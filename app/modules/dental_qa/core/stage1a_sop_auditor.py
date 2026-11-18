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
from app.modules.dental_qa.core.gemini_caller import execute_gemini_structured_call

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
    """Executes Stage 1A: Dental SOP audit with rate-limit resilient Gemini caller."""
    prompt = f"{SYSTEM_PROMPT_SOP_AUDITOR}\n\n[CONVERSATION TRANSCRIPT TO AUDIT]:\n{transcript}"
    return await execute_gemini_structured_call(
        prompt=prompt,
        schema=DentalSOPAuditResponse,
        stage_name="Stage 1A Dental SOP Audit",
        model_name=model_name,
        timeout=timeout,
    )

