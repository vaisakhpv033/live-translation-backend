import json
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Tuple
import httpx
from app.core.config import get_settings

logger = logging.getLogger("translation-agent-backend.services.evaluation_service")
settings = get_settings()

# ──────────────────────────────────────────────────────────────
#  Gemini QA Report Card Schema (structured JSON output)
# ──────────────────────────────────────────────────────────────

GEMINI_QA_REPORT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "scenario_practiced": {
            "type": "STRING",
            "description": "Brief summary of customer profile and situation"
        },
        "overall_score": {
            "type": "INTEGER",
            "description": "Overall score from 1 to 100"
        },
        "rapport": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "discovery": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "product_knowledge": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "communication": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "objection_handling": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "recommendation_quality": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "compliance": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "closing": {
            "type": "OBJECT",
            "properties": {
                "score": {"type": "INTEGER", "description": "Score from 1 to 10"},
                "reason": {"type": "STRING", "description": "Short explanation or evidence for the score"}
            },
            "required": ["score", "reason"]
        },
        "positives": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of strongest behaviors observed (empty list if none)"
        },
        "improvement_areas": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of the most important weaknesses/improvements"
        },
        "missed_opportunities": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of important questions that should have been asked"
        },
        "compliance_issues": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "List of compliance concerns/violations (empty list if none)"
        },
        "coaching_recommendations": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "description": "3 specific coaching recommendations"
        },
        "readiness_assessment": {
            "type": "STRING",
            "description": "Readiness assessment (must be one of: 'Not Ready', 'Needs Significant Coaching', 'Developing', 'Ready With Supervision', 'Production Ready')"
        },
        "readiness_reasoning": {
            "type": "STRING",
            "description": "Detailed reasoning for the readiness assessment"
        }
    },
    "required": [
        "scenario_practiced",
        "overall_score",
        "rapport",
        "discovery",
        "product_knowledge",
        "communication",
        "objection_handling",
        "recommendation_quality",
        "compliance",
        "closing",
        "positives",
        "improvement_areas",
        "missed_opportunities",
        "compliance_issues",
        "coaching_recommendations",
        "readiness_assessment",
        "readiness_reasoning"
    ]
}

# ──────────────────────────────────────────────────────────────
#  Scenario-Specific System Prompts
# ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT_SBI = """You are an expert SBI Mutual Fund sales trainer and quality analyst.
Your task is to evaluate the conversation between a sales representative and a prospective customer.
Evaluate the sales representative only. Do not evaluate the customer.
Use the entire conversation transcript as evidence. Be objective and specific.
Do not invent information that was not present in the conversation.

Evaluate based on the following criteria:
1. Rapport & Professionalism
2. Discovery & Needs Analysis
3. Product Knowledge
4. Communication Skills
5. Objection Handling
6. Recommendation Quality
7. Compliance & Ethical Conduct
8. Closing Effectiveness"""

SYSTEM_PROMPT_WTW = """You are an expert Willis Towers Watson (WTW) benefits helpdesk quality analyst.
Your task is to evaluate the conversation between a benefits helpdesk analyst and an employee caller.
Evaluate the helpdesk analyst ONLY. Do not evaluate the caller.
Use the entire conversation transcript as evidence. Be objective and specific.
Do not invent information that was not present in the conversation.

This is a WTW corporate benefits helpdesk call. The caller is an employee asking about a denied insurance claim and plan options.

Evaluate based on the following criteria (mapped to the scoring categories):

1. Rapport & Professionalism — Was the analyst professional, empathetic, and courteous?
2. Discovery & Verification — Did the analyst properly verify the caller's identity WITHOUT reading back sensitive PII (SSN, DOB digits)? CRITICAL: If the analyst read back any SSN digits or full date of birth to the caller, this is a SEVERE compliance violation and must be scored 1-2.
3. Product Knowledge (Plan & Policy Accuracy) — Did the analyst accurately explain plan rules? CRITICAL: If the analyst stated that mid-year plan changes are allowed without mentioning Qualifying Life Events (QLE) or Open Enrollment periods, this is an ACCURACY ERROR and must be scored 1-3.
4. Communication Skills — Did the analyst explain out-of-network vs in-network coverage clearly and in plain language?
5. Objection Handling (Caller Frustration Management) — How well did the analyst handle the caller's frustration about the denied claim?
6. Recommendation Quality (Guidance & Next Steps) — Did the analyst provide actionable next steps (appeal process, finding in-network providers, etc.)?
7. Compliance & Privacy Guardrails — Overall compliance assessment. ANY PII exposure (reading back SSN/DOB digits) is an automatic critical failure. Any inaccurate eligibility statements are compliance violations.
8. Closing Effectiveness — Did the analyst summarize the resolution, confirm next steps, and close the call professionally?

PAY SPECIAL ATTENTION TO THESE TWO PLANTED SCENARIOS:
- PII EXPOSURE: If the analyst reads back, confirms, or repeats any digits of the caller's SSN or date of birth, flag this as a CRITICAL compliance violation in compliance_issues and score Discovery/Verification and Compliance categories severely (1-2 out of 10).
- ELIGIBILITY ACCURACY: If the analyst says the caller can switch plans mid-year without mentioning QLE or Open Enrollment, flag this as an ACCURACY ERROR in compliance_issues and score Product Knowledge severely (1-3 out of 10).

If the analyst correctly refuses to read back PII and correctly states that mid-year changes require a QLE, acknowledge these as strong compliance behaviors in positives."""

SYSTEM_PROMPT_LIVE_CALL = """You are an expert health insurance quality analyst and sales coach.
Your task is to evaluate the conversation between a health insurance representative and a customer.
Evaluate the representative ONLY. Do not evaluate the customer.
Use the entire conversation transcript as evidence. Be objective and specific.
Do not invent information that was not present in the conversation.

Evaluate based on the following criteria (mapped to the scoring categories):
1. Rapport & Professionalism — Did the representative show empathy, professional greeting, and tone?
2. Discovery & Needs Analysis — Did the representative ask questions to understand the customer's medical history, current coverage, and specific healthcare needs?
3. Product Knowledge — Did the representative explain health insurance policies, deductibles, copayments, and in-network vs out-of-network coverage accurately?
4. Communication Skills — Was the explanation of complex health insurance terms clear and easy to understand?
5. Objection Handling — How well did the representative address concerns about premium costs, coverage exclusions, or denied claims?
6. Recommendation Quality — Did the representative suggest appropriate plans based on the customer's budget and medical requirements?
7. Compliance & Privacy Guardrails — Did the representative adhere to HIPAA or local regulations, ensuring customer details and PII (like full date of birth, SSN, or clinical history) are handled securely without reading back sensitive information unprompted?
8. Closing Effectiveness — Did the representative summarize next steps, confirm understanding, and close the call professionally?"""

SCENARIO_PROMPTS = {
    "sbi": SYSTEM_PROMPT_SBI,
    "wtw": SYSTEM_PROMPT_WTW,
    "live call": SYSTEM_PROMPT_LIVE_CALL,
    "live-call": SYSTEM_PROMPT_LIVE_CALL,
}


# ──────────────────────────────────────────────────────────────
#  Evaluation Service Interface and Implementation
# ──────────────────────────────────────────────────────────────

class IEvaluationService(ABC):
    """
    Interface for chat transcript evaluation (Interface Segregation).
    """
    @abstractmethod
    async def evaluate_chat_history(
        self, chat_history_str: Optional[str], scenario: Optional[str] = "sbi"
    ) -> Tuple[Optional[dict], int]:
        """
        Evaluates a chat transcript and returns (report_card_dict, overall_score).
        Returns (None, 0) on failure.
        """
        pass


class GeminiEvaluationService(IEvaluationService):
    """
    Gemini-backed evaluation service (migrated from report-server/services/gemini.py).
    Calls the Gemini API with structured JSON output to generate a QA report card.
    """

    async def evaluate_chat_history(
        self, chat_history_str: Optional[str], scenario: Optional[str] = "sbi"
    ) -> Tuple[Optional[dict], int]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            logger.error("Gemini API key not configured.")
            return None, 0

        transcript = self._format_transcript(chat_history_str)

        system_prompt = SCENARIO_PROMPTS.get(scenario or "sbi", SYSTEM_PROMPT_SBI)
        prompt = f"{system_prompt}\n\nHere is the conversation transcript:\n{transcript}"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": GEMINI_QA_REPORT_SCHEMA
            }
        }

        max_retries = 3
        backoff_factor = 2.0

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(url, headers=headers, json=payload)
                    
                    if response.status_code == 200:
                        response_json = response.json()
                        candidates = response_json.get("candidates", [])
                        if not candidates:
                            logger.error(f"No candidates returned from Gemini: {response_json}")
                            return None, 0

                        content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if not content_text:
                            logger.error("Empty text in Gemini response candidate.")
                            return None, 0

                        report_card = json.loads(content_text.strip())
                        overall_score = report_card.get("overall_score", 0)
                        return report_card, overall_score
                    
                    if response.status_code in [429, 500, 502, 503, 504]:
                        logger.warning(
                            f"Gemini API returned status {response.status_code}. "
                            f"Attempt {attempt + 1} of {max_retries}. Retrying..."
                        )
                    else:
                        logger.error(f"Gemini API returned unrecoverable status {response.status_code}: {response.text}")
                        return None, 0
                        
            except (httpx.RequestError, json.JSONDecodeError) as e:
                logger.warning(f"Error during Gemini call attempt {attempt + 1}: {e}")
                
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                await asyncio.sleep(sleep_time)
                
        logger.error("Gemini API call failed after max retries.")
        return None, 0

    @staticmethod
    def _format_transcript(chat_history_str: Optional[str]) -> str:
        """Parses LiveKit chat history JSON into a readable transcript."""
        if not chat_history_str:
            return "No transcript available."
        try:
            data = json.loads(chat_history_str)
            items = data.get("items", [])
            lines = []
            for item in items:
                if item.get("type") != "message":
                    continue
                role = item.get("role")
                if role == "system":
                    continue

                content_list = item.get("content", [])
                text = ""
                if isinstance(content_list, list):
                    text = " ".join([str(c) for c in content_list if isinstance(c, str)])
                elif isinstance(content_list, str):
                    text = content_list

                if not text.strip():
                    continue

                speaker = "Ira Representative" if role == "user" else "AI Customer"
                lines.append(f"{speaker}: {text.strip()}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error parsing transcript: {e}"
