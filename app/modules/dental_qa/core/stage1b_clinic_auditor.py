"""
Stage 1B: Clinic Protocol Auditor (Citrus Smiles Dental)
Evaluates transcript strictly against Citrus Smiles onboarding protocols.
"""

import json
import logging
import asyncio
from typing import Optional
import httpx
from pydantic import ValidationError

from app.modules.dental_qa.config import settings
from app.modules.dental_qa.protocols import format_citrus_protocol_for_prompt
from app.modules.dental_qa.schemas import ClinicProtocolAuditResponse
from app.modules.dental_qa.core.gemini_caller import execute_gemini_structured_call

logger = logging.getLogger("dental_qa_engine.stage1b")

SYSTEM_PROMPT_CLINIC_AUDITOR = f"""You are a specialized Dental Practice Quality Auditor evaluating a Front Desk Trainee at Citrus Smiles Dental.
Your SOLE responsibility is to audit the conversation transcript strictly against the Citrus Smiles Clinic Protocol provided below.

INSTRUCTIONS:
1. Pay paramount attention to TIER 1 HARD COMPLIANCE RULES:
   - Operating Hours: Open Mon, Tue, Thu, Fri (10am-6pm Central). Strictly CLOSED Wed, Sat, Sun.
   - Prepayments: NEVER demand or collect credit card prepayment over the phone.
   - Insurance: Accepts PPOs and Medicaid. STRICTLY NO HMO. Doctor order: book patient and do not argue insurance.
   - Cancellations: Requires 48 business hours advance notice.
2. Check TIER 2 TRIGGER-BASED RULES if raised during conversation:
   - Lead Provider: Dr. Mahima Gupta (Leading US Implantologist).
   - Address / Landmark: 1629 Smirl Dr #101, Heath TX (behind Standard Service, next to CVS).
   - Minimum Patient Age: 1 year old. Parents allowed in operatory: Yes.
   - Promotions: $1 Implant Consultation. Fee waivable for shopping around.
   - Special Note: Trainee MUST ask how many teeth are missing on implant inquiries.
   - Attendance: $50/hour no-show fee, 15-minute late grace period, max 2 reschedules.
3. For every triggered clinic rule, extract exact verbatim quotes, evaluate compliance verdict, and explain violation details.
4. Assign a raw 'clinic_protocol_adherence_score' from 1 to 10:
   - 9-10: Perfect compliance with all clinic guidelines.
   - 7-8: Followed all core rules, minor omissions on landmarks or promotions.
   - 5-6: Missed secondary protocol (e.g. forgot to ask missing teeth count on implant call).
   - 3-4: Violated 1 major rule (e.g. debated insurance extensively, quoted 24h cancellation instead of 48h).
   - 1-2: CRITICAL FAILURE: Offered/booked appointment on closed day (Wed/Sat/Sun) or demanded phone prepayment.

{format_citrus_protocol_for_prompt()}
"""

async def audit_clinic_protocols(
    transcript: str,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> tuple[ClinicProtocolAuditResponse, dict]:
    """Executes Stage 1B: Clinic Protocol audit with rate-limit resilient Gemini caller."""
    prompt = f"{SYSTEM_PROMPT_CLINIC_AUDITOR}\n\n[CONVERSATION TRANSCRIPT TO AUDIT]:\n{transcript}"
    return await execute_gemini_structured_call(
        prompt=prompt,
        schema=ClinicProtocolAuditResponse,
        stage_name="Stage 1B Clinic Protocol Audit",
        model_name=model_name,
        timeout=timeout,
    )

