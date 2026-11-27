"""Dedicated Gemini QA evaluation service for USV Doctor Detailing sessions."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from app.core.config import get_settings
from app.modules.usv_doctor.prompts import (
    USV_DOCTOR_EVALUATION_PROMPT,
    USV_DOCTOR_QA_SCHEMA,
)

logger = logging.getLogger("translation-agent-backend.modules.usv_doctor.evaluation")
settings = get_settings()


class UsvDoctorEvaluationService:
    """Evaluates USV Doctor Detailing call transcripts and returns report card + Gemini usage metrics."""

    @staticmethod
    def format_transcript(chat_history_raw: Any) -> str:
        """Formats stored chat history into labeled representative/physician dialogue lines."""
        if not chat_history_raw:
            return ""

        data = chat_history_raw
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                return ""

        items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        lines: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if "type" in item and item.get("type") not in ("message", "text", "transcript"):
                continue

            role = (item.get("role") or "").strip().lower()
            if role in ("system", "tool"):
                continue

            content = item.get("content", "")
            text = ""
            if isinstance(content, list):
                text = " ".join(str(part) for part in content if isinstance(part, str)).strip()
            elif isinstance(content, str):
                text = content.strip()

            if not text:
                for key in ("text", "message", "transcript"):
                    fallback = item.get(key)
                    if isinstance(fallback, str) and fallback.strip():
                        text = fallback.strip()
                        break

            if not text:
                continue

            speaker = (
                "Medical Sales Representative"
                if role in ("user", "trainee", "human")
                else "AI Physician"
            )
            lines.append(f"{speaker}: {text}")

        return "\n".join(lines)

    @staticmethod
    def build_context_block(session_metadata: Optional[Dict[str, Any]]) -> str:
        """Formats physician persona metadata into an evaluation context block."""
        if not isinstance(session_metadata, dict) or not session_metadata:
            return ""

        fields = [
            ("Scenario Title", session_metadata.get("title")),
            ("Physician Name", session_metadata.get("doctor_name")),
            ("Physician Specialty", session_metadata.get("doctor_specialty")),
            ("Clinic Setting", session_metadata.get("clinic_setting")),
            ("Physician Demeanor", session_metadata.get("demeanor")),
            ("Current Standard of Care", session_metadata.get("current_standard_of_care")),
            ("Representative", session_metadata.get("trainee_name")),
            ("Language", session_metadata.get("language")),
        ]
        present = [f"- {label}: {val}" for label, val in fields if val]
        if not present:
            return ""
        return "[PHYSICIAN & CALL CONTEXT]\n" + "\n".join(present) + "\n[END CONTEXT]"

    @staticmethod
    def _empty_transcript_card() -> dict:
        no_data_reason = "No call dialogue recorded. Evaluation cannot be performed because no conversation occurred."
        return {
            "scenario_practiced": "No call dialogue recorded during this session.",
            "overall_score": 0,
            "readiness_assessment": "Not Ready",
            "readiness_reasoning": "No call data available. The session contained no spoken dialogue to evaluate.",
            "rapport": {"score": 0, "reason": no_data_reason},
            "discovery": {"score": 0, "reason": no_data_reason},
            "product_knowledge": {"score": 0, "reason": no_data_reason},
            "communication": {"score": 0, "reason": no_data_reason},
            "objection_handling": {"score": 0, "reason": no_data_reason},
            "recommendation_quality": {"score": 0, "reason": no_data_reason},
            "compliance": {"score": 0, "reason": no_data_reason},
            "closing": {"score": 0, "reason": no_data_reason},
            "positives": [],
            "improvement_areas": ["Ensure microphone audio and connection are active so dialogue can be captured."],
            "missed_opportunities": [],
            "compliance_issues": [],
            "coaching_recommendations": ["Verify audio setup and run a full detailing simulation."],
        }

    async def evaluate_transcript(
        self,
        chat_history_raw: Any,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[dict], int, dict]:
        """Runs Gemini structured QA analysis and returns (report_card, overall_score, qa_usage_info)."""
        transcript = self.format_transcript(chat_history_raw)
        if not transcript.strip():
            logger.warning("Empty transcript in USV Doctor evaluation; returning zero-score card.")
            return self._empty_transcript_card(), 0, {"model_name": None, "usage_metadata": {}}

        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.error("GEMINI_API_KEY is not configured for USV Doctor evaluation.")
            return None, 0, {}

        model_name = getattr(settings, "GEMINI_EVALUATION_MODEL", None) or "gemini-4-hydrogen"
        thinking_level = getattr(settings, "GEMINI_EVALUATION_THINKING_LEVEL", None) or "low"
        context_block = self.build_context_block(session_metadata)
        prompt_parts = [USV_DOCTOR_EVALUATION_PROMPT]
        if context_block:
            prompt_parts.append(context_block)
        prompt_parts.append(f"Conversation Transcript:\n{transcript}")
        prompt = "\n\n".join(prompt_parts)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": USV_DOCTOR_QA_SCHEMA,
                "thinkingConfig": {
                    "thinkingLevel": thinking_level,
                },
            },
        }

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, headers=headers, json=payload)

                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if not candidates:
                            logger.error(f"No candidates returned from Gemini: {data}")
                            return None, 0, {}

                        parts = candidates[0].get("content", {}).get("parts", [])
                        content_text = "".join(
                            p.get("text", "") for p in parts if not p.get("thought", False)
                        )
                        if not content_text.strip():
                            logger.error("Empty text in Gemini QA response candidate.")
                            return None, 0, {}

                        report_card = json.loads(content_text.strip())
                        overall_score = int(report_card.get("overall_score", 0))
                        usage_metadata = data.get("usageMetadata", {}) or {}
                        return report_card, overall_score, {
                            "model_name": model_name,
                            "usage_metadata": usage_metadata,
                        }

                    if response.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            f"Gemini QA returned {response.status_code} on attempt {attempt + 1}/{max_retries}."
                        )
                    else:
                        logger.error(
                            f"Gemini QA unrecoverable status {response.status_code}: {response.text}"
                        )
                        return None, 0, {}

            except (httpx.RequestError, json.JSONDecodeError, ValueError) as exc:
                logger.warning(f"USV Doctor QA attempt {attempt + 1} error: {exc}")

            if attempt < max_retries - 1:
                await asyncio.sleep(backoff_factor ** attempt)

        logger.error("USV Doctor QA evaluation failed after max retries.")
        return None, 0, {}
