"""
Stage 2: Holistic Behavioral & Communication Evaluator
Grades the remaining 7 communication/behavioral dimensions and synthesizes qualitative coaching sections.
"""

import json
import logging
import asyncio
from typing import Optional, List, Dict, Any
import httpx
from pydantic import ValidationError

from app.modules.dental_qa.config import settings
from app.modules.dental_qa.schemas import (
    BehavioralEvaluationResponse,
    DentalSOPAuditItem,
    ClinicProtocolAuditItem,
)
from app.modules.dental_qa.schemas.gemini_schema import to_gemini_schema

logger = logging.getLogger("dental_qa_engine.stage2")

SYSTEM_PROMPT_BEHAVIORAL_EVALUATOR = """You are an expert Dental Front Desk Quality Analyst, Patient Experience Trainer, and Call Center Coach.
Your task is to evaluate the interpersonal, communication, diagnostic, and clinical compliance skills of a Dental Front Desk Trainee.
Evaluate the Front Desk Trainee ONLY. Do NOT evaluate the patient.

You have been provided with:
1. The full conversation transcript.
2. The Stage 1A Dental SOP Audit findings (verdicts and quotes).
3. The Stage 1B Clinic Protocol Audit findings (verdicts and quotes).

EVALUATE THE FOLLOWING 7 CORE DIMENSIONS (Scored 1 to 10 with evidence-based reasoning):
1. Rapport & Professionalism (1-10): Warm greeting, empathy, identifying self & practice, treating caller like family.
2. Discovery & Needs Analysis (1-10): Pain level, duration, teeth affected, triggers, past dental history, urgency triage.
3. Communication Skills (1-10): Plain language, jargon-free explanations, conversational pacing, active listening.
4. Objection Handling (1-10): Resolving friction regarding cost, doctor requests, or scheduling with empathy and value.
5. Recommendation Quality (1-10): Matching caller needs to appropriate appointment slot (emergency vs comprehensive vs consult).
6. Compliance & Ethical Conduct (1-10): HIPAA adherence, no medical diagnosis over phone, no unauthorized payment/approval guarantees.
7. Closing Effectiveness (1-10): Confirming date, time, doctor, office address/landmark, paperwork buffer (30m early), warm sign-off.

ALSO SYNTHESIZE THE FOLLOWING QUALITATIVE SECTIONS:
- call_summary: Concise 2-3 sentence overview of caller situation and trainee handling.
- strengths: List of top positive behaviors observed.
- improvement_opportunities: Specific coaching areas where trainee fell short.
- missed_opportunities: High-value opportunities missed (promotions, diagnostic questions).
- compliance_review_security: Structured audit of PCI-DSS prepayment adherence, HIPAA, and password security.
- coaching_recommendations: 2-3 specific, actionable roleplay drills.
- assessment_reasoning_justification: Detailed narrative explaining the holistic evaluation.
"""

async def evaluate_behavioral_dimensions(
    transcript: str,
    sop_audits: List[DentalSOPAuditItem],
    clinic_audits: List[ClinicProtocolAuditItem],
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> tuple[BehavioralEvaluationResponse, dict]:
    """Executes Stage 2: Holistic Behavioral Evaluation with Gemini thinking mode."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    model = model_name or settings.GEMINI_MODEL
    http_timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    # Format Stage 1 context for the evaluator
    audit_context = (
        f"### STAGE 1A DENTAL SOP AUDIT FINDINGS ({len(sop_audits)} items):\n"
        f"{json.dumps([item.model_dump() for item in sop_audits], indent=2)}\n\n"
        f"### STAGE 1B CLINIC PROTOCOL AUDIT FINDINGS ({len(clinic_audits)} items):\n"
        f"{json.dumps([item.model_dump() for item in clinic_audits], indent=2)}"
    )

    prompt = (
        f"{SYSTEM_PROMPT_BEHAVIORAL_EVALUATOR}\n\n"
        f"[VERIFIED AUDIT FINDINGS FROM STAGE 1]:\n{audit_context}\n\n"
        f"[CONVERSATION TRANSCRIPT]:\n{transcript}"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": to_gemini_schema(BehavioralEvaluationResponse),
            "thinkingConfig": {
                "thinkingLevel": settings.GEMINI_THINKING_LEVEL
            }
        }
    }

    max_retries = settings.MAX_RETRIES
    backoff = settings.BACKOFF_FACTOR

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=http_timeout) as client:
                res = await client.post(url, headers=headers, json=payload)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise ValueError(f"No candidates returned in Gemini response: {data}")

                    # Safe extraction: concatenate non-thought parts
                    parts = candidates[0].get("content", {}).get("parts", [])
                    raw_text = "".join(p.get("text", "") for p in parts if not p.get("thought", False))
                    if not raw_text.strip():
                        finish_reason = candidates[0].get("finishReason", "UNKNOWN")
                        raise ValueError(f"Empty text in Gemini response candidate (finishReason: {finish_reason})")

                    parsed_dict = json.loads(raw_text.strip())
                    usage = data.get("usageMetadata", {})
                    return BehavioralEvaluationResponse.model_validate(parsed_dict), usage

                if res.status_code in [429, 500, 502, 503, 504]:
                    logger.warning(f"Gemini Stage 2 returned status {res.status_code}. Retrying attempt {attempt + 1}/{max_retries}...")
                else:
                    raise RuntimeError(f"Unrecoverable error in Stage 2 (status {res.status_code}): {res.text}")

        except (httpx.RequestError, json.JSONDecodeError, ValueError, ValidationError) as e:
            err_msg = str(e) or "Socket/Read Timeout"
            logger.warning(f"Stage 2 attempt {attempt + 1} failed: {type(e).__name__}: {err_msg}")

        if attempt < max_retries - 1:
            await asyncio.sleep(backoff ** attempt)

    raise TimeoutError("Stage 2 Behavioral Evaluation failed after max retries.")

