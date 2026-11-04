"""
Stage 1A: Dental Front Desk SOP Auditor
Evaluates transcript strictly against the 41 general Dental SOP rules.
"""

import json
import logging
import asyncio
from typing import Optional
import httpx
from pydantic import ValidationError

from app.modules.dental_qa.config import settings
from app.modules.dental_qa.protocols import format_sop_rules_for_prompt
from app.modules.dental_qa.schemas import DentalSOPAuditResponse
from app.modules.dental_qa.schemas.gemini_schema import to_gemini_schema

logger = logging.getLogger("dental_qa_engine.stage1a")

SYSTEM_PROMPT_SOP_AUDITOR = f"""You are a specialized Dental Front Desk Standard Operating Procedure (SOP) Auditor.
Your SOLE responsibility is to audit the conversation transcript between a Dental Front Desk Trainee and a Patient strictly against the 41 official Dental SOP rules provided below.

INSTRUCTIONS:
1. Identify every instance where the patient triggers an objection, inquiry, or challenge that corresponds to one of the 41 SOP rules.
2. For every triggered rule:
   - Extract the verbatim quote from the caller (`patient_trigger_quote`).
   - Extract the verbatim quote of the trainee's actual spoken response (`trainee_actual_quote`).
   - Determine the compliance verdict: 'Adhered', 'Partially Adhered', 'Violated', or 'Missed Opportunity'.
   - Detail specifically what was followed, missing, or breached in `violation_details`.
   - Cite the approved verbiage guidance from the SOP rule.
3. If no specific SOP scenarios were triggered, 'sop_audit_table' must be an empty list [].
4. Assign a raw 'dental_sop_adherence_score' from 1 to 10 with clear justification:
   - 9-10: Flawlessly followed all triggered SOP verbiages and protocols.
   - 7-8: Standard adherence with minor verbal deviations, no major protocol breaches.
   - 5-6: Inconsistent; missed 1 secondary rule or delivered incomplete verbiage.
   - 3-4: Violated 1 major SOP rule (e.g. put caller on hold to search for doctor, dead air > 5s without pause notice).
   - 1-2: Violated 2+ major SOP rules or defied practice protocols.

{format_sop_rules_for_prompt()}
"""

async def audit_dental_sops(
    transcript: str,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> tuple[DentalSOPAuditResponse, dict]:
    """Executes Stage 1A: Dental SOP audit with Gemini thinking mode."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    model = model_name or settings.GEMINI_MODEL
    http_timeout = timeout or settings.HTTP_TIMEOUT_SECONDS

    prompt = f"{SYSTEM_PROMPT_SOP_AUDITOR}\n\n[CONVERSATION TRANSCRIPT TO AUDIT]:\n{transcript}"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": to_gemini_schema(DentalSOPAuditResponse),
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
                    return DentalSOPAuditResponse.model_validate(parsed_dict), usage

                if res.status_code in [429, 500, 502, 503, 504]:
                    logger.warning(f"Gemini Stage 1A returned status {res.status_code}. Retrying attempt {attempt + 1}/{max_retries}...")
                else:
                    raise RuntimeError(f"Unrecoverable error in Stage 1A (status {res.status_code}): {res.text}")

        except (httpx.RequestError, json.JSONDecodeError, ValueError, ValidationError) as e:
            err_msg = str(e) or "Socket/Read Timeout"
            logger.warning(f"Stage 1A attempt {attempt + 1} failed: {type(e).__name__}: {err_msg}")

        if attempt < max_retries - 1:
            await asyncio.sleep(backoff ** attempt)

    raise TimeoutError("Stage 1A Dental SOP Audit failed after max retries.")

