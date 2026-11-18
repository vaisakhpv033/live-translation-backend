"""
Stage 1C: Voice Rating Parameters Auditor (IRA AI SOP)
Evaluates conversation against 27 granular Voice Rating Parameters across 5 sessions:
- Block A: Opening (A1 to A4)
- Block B: Initial Addressal (B1 to B2)
- Block C: Persuasion (C1 to C5)
- Block D: Closure (D1 to D4)
- Block E: Overall Communication (E1 to E12)

Architecture:
- Splits LLM workload into 2 concurrent sub-calls (Blocks A-D, and Block E) to avoid token truncation.
- Parameter E2 (Dead Air > 45s) is evaluated deterministically from watchdog telemetry.
- Standardized verdicts: 'followed', 'partially followed', 'not followed', 'not possible to analyze'.
"""

import json
import logging
import asyncio
from typing import Optional, Tuple, Dict, Any, List
import httpx
from pydantic import ValidationError

from app.modules.dental_qa.config import settings
from app.modules.dental_qa.schemas.gemini_schema import to_gemini_schema
from app.modules.dental_qa.core.gemini_caller import execute_gemini_structured_call
from app.modules.dental_qa.schemas.voice_rating import (
    VoiceVerdict,
    VoiceRatingParameterItem,
    VoiceRatingSessionBlock,
    VoiceRatingAuditResponse,
    Stage1CBlocksABCDRawResponse,
    Stage1CBlockERawResponse,
)

logger = logging.getLogger("dental_qa_engine.stage1c")

# ==============================================================================
# SUB-CALL 1: SYSTEM PROMPT FOR STRUCTURAL BLOCKS A, B, C, D (15 Parameters)
# ==============================================================================
SYSTEM_PROMPT_BLOCKS_ABCD = """You are a senior Quality Assurance auditor evaluating a Dental Front Desk Trainee according to the official IRA AI SOP Voice Rating Parameters.
Your task is to audit the conversation transcript strictly for the 15 parameters in Blocks A, B, C, and D.

For each parameter, assign one of four standardized verdicts:
- "followed": The requirement was fully and properly executed.
- "partially followed": The requirement was partially met, delayed, or contained minor errors.
- "not followed": The trainee omitted the requirement or breached protocol.
- "not possible to analyze": The call was dropped/disconnected or the situation did not present an opportunity.

Provide the exact parameter code, the evaluation question, the verdict, a verbatim evidence quote (if applicable), and detailed reasoning.

PARAMETERS TO EVALUATE:

--- BLOCK A: OPENING ---
A1. Deliver a proper greeting that included his/her name and the name of the practice?
    - Question: "deliver a proper greeting that included his/her name and the name of the practice?"
    - followed: Trainee stated both their name and the clinic name ("Citrus Smiles Dental").
    - partially followed: Stated practice name but omitted own name, or vice versa.
    - not followed: Casual greeting without practice or trainee identity.
    - not possible to analyze: Call disconnected before greeting.

A2. Offer to help the caller?
    - Question: "offer to help the caller ?"
    - followed: Explicit verbal offer to assist (e.g., "How may I help you today?").
    - partially followed: Passive or terse acknowledgement (e.g., "Yes?", "What do you need?").
    - not followed: Jumped directly into questioning without offering assistance.
    - not possible to analyze: Immediate disconnect.

A3. Ask for the caller's name and verify the number?
    - Question: "ask for the callers name and verify the number ?"
    - followed: Trainee asked for caller's name AND verified callback phone number.
    - partially followed: Obtained caller name but missed phone verification, or vice versa.
    - not followed: Neither name nor number requested/verified.
    - not possible to analyze: Caller disconnected before intake.

A4. Ask whether the caller is a new patient or not before scheduling the appointment in Dentrix?
    - Question: "ask whether the caller is a new patient or not before scheduling the appointment in Dentrix, so that we can ask the patient to press 1 at the right time?"
    - followed: Explicitly checked new vs. existing patient status before checking or booking slots.
    - partially followed: Asked patient status late in call after discussing slots.
    - not followed: Scheduled without ever clarifying patient status.
    - not possible to analyze: Inquiry did not involve scheduling.

--- BLOCK B: INITIAL ADDRESSAL ---
B1. Probe the caller in order to ascertain the nature of his/her query/issue?
    - Question: "probe the caller inorder to ascertain the nature of his/her query/issue?"
    - followed: Trainee asked clarifying diagnostic questions (chief complaint, pain level, symptoms).
    - partially followed: Accepted vague statement without probing details.
    - not followed: Ignored complaint or failed to probe.
    - not possible to analyze: Caller exhaustively explained everything upfront without need to probe.

B2. Offer the appropriate solution to the caller?
    - Question: "offer the appropriate solution to the caller?"
    - followed: Offered correct clinical solution (emergency same-day exam for severe pain, comprehensive exam for new patient).
    - partially followed: Incomplete or delayed solution (e.g. routine cleaning 2 weeks out for acute toothache).
    - not followed: Incorrect/unauthorized solution (prescribing medication, improper refusal).
    - not possible to analyze: Disconnected before solution stage.

--- BLOCK C: PERSUASION ---
C1. Display adequate subject matter knowledge during the conversation?
    - Question: "display adequate subject matter knowledge during the conversation?"
    - followed: Accurately explained dental procedures and terminology with confidence.
    - partially followed: Minor hesitation or slight inaccuracy on non-critical terms.
    - not followed: Severe confusion or false clinical claims.
    - not possible to analyze: Call too brief to assess clinical knowledge.

C2. Highlight the merits of the Doctor and the practice during the conversation?
    - Question: "highlight the merits of the Doctor and the practice during the conversation?"
    - followed: Mentioned Dr. Mahima Gupta's credentials/expertise or practice merits (modern tech, gentle care).
    - partially followed: Generic mention of clinic without highlighting merits.
    - not followed: Missed opportunity to reassure a hesitant caller.
    - not possible to analyze: Acute emergency where marketing/merits would be inappropriate.

C3. Offer appropriate (up to 2 and no more) rebuttals for the objections raised by the caller?
    - Question: "offer appropriate (upto 2 and no more) rebuttals for the objections raised by the caller?"
    - followed: Provided 1 or 2 polite, value-focused rebuttals to hesitation or objections.
    - partially followed: Weak rebuttal or overly pushy (>2 aggressive rebuttals).
    - not followed: Conceded immediately with 0 rebuttals or argued hostilely.
    - not possible to analyze: No objections were raised by caller.

C4. Explain the rates, procedure & timings properly?
    - Question: "explain the rates, procedure & timings properly?"
    - followed: Clearly communicated fees/promotions ($1 implant consult), arrival time (30 min early for paperwork), and duration.
    - partially followed: Explained procedure but vague on pricing/arrival time, or vice versa.
    - not followed: Misquoted rates, promised unauthorized discounts, or hid fees.
    - not possible to analyze: Rates/procedures were not relevant to caller's inquiry.

C5. Volunteer to book an appointment for the caller during the conversation?
    - Question: "volunteer to book an appointment for the caller during the conversation?"
    - followed: Proactively offered specific appointment days/times ("Would Thursday at 2 PM work?").
    - partially followed: Waited for caller to explicitly ask to book.
    - not followed: Pushed booking onus back to caller ("Call us back when you know").
    - not possible to analyze: Non-booking inquiry (billing, vendor).

--- BLOCK D: CLOSURE ---
D1. Paraphrase the caller's query/issue and the solution offered during the call?
    - Question: "paraphrase the caller's query/issue and the solution offered during the call?"
    - followed: Recapped appointment date, time, provider (Dr. Gupta), and agreed next steps.
    - partially followed: Confirmed date/time but missed provider or instructions.
    - not followed: Ended call without recapping agreed details.
    - not possible to analyze: Caller disconnected abruptly before closure.

D2. Insist on the prospect sending the paperwork in advance during the conversation?
    - Question: "insist on the prospect sending the paperwork in advance during the conversation?"
    - followed: Explicitly instructed patient to complete intake paperwork online prior to arrival.
    - partially followed: Mentioned paperwork casually without emphasizing doing it in advance.
    - not followed: Failed to mention paperwork for a new patient booking.
    - not possible to analyze: Existing patient with current paperwork on file or non-booking call.

D3. Check with the caller whether he/she had answered all of the queries before concluding the conversation?
    - Question: "check with the caller whether he/she had answered all of the queries before concluding the conversation ?"
    - followed: Trainee explicitly asked if caller had any further questions ("Is there anything else I can help you with today?").
    - partially followed: Rushed or mumbled check.
    - not followed: Ended without asking if all queries were answered.
    - not possible to analyze: Sudden caller disconnect.

D4. Wish the caller appropriately before concluding the conversation?
    - Question: "wish the caller appropriately before concluding the conversation?"
    - followed: Delivered warm, professional closing pleasantry ("Thank you for calling Citrus Smiles, have a wonderful day!").
    - partially followed: Abrupt or informal goodbye ("Bye", "Yup").
    - not followed: Hung up in silence without saying goodbye.
    - not possible to analyze: Sudden disconnection.

Return strictly valid JSON matching the schema with all 15 parameters audited.
"""

# ==============================================================================
# SUB-CALL 2: SYSTEM PROMPT FOR HOLISTIC BLOCK E (11 Parameters, E2 omitted)
# ==============================================================================
SYSTEM_PROMPT_BLOCK_E = """You are a senior Quality Assurance auditor evaluating a Dental Front Desk Trainee according to the official IRA AI SOP Voice Rating Parameters.
Your task is to audit the conversation transcript strictly for the 11 communication parameters in Block E (Overall Communication).
NOTE: Parameter E2 (Dead Air > 45s) is evaluated deterministically by the telemetry system and is OMITTED from your evaluation. You must evaluate ONLY: E1, E3, E4, E5, E6, E7, E8, E9, E10, E11, E12.

For each parameter, assign one of four standardized verdicts:
- "followed": The requirement was fully and properly executed.
- "partially followed": The requirement was partially met, inconsistent, or contained minor errors.
- "not followed": The trainee omitted the requirement or exhibited unprofessional behavior.
- "not possible to analyze": The call was dropped or transcript data lacks acoustic/interactional evidence.

PARAMETERS TO EVALUATE:

E1. Express empathy over the caller's situation?
    - Question: "express empathy over the caller's situation ?"
    - followed: Sincere, timely empathy expressed ("I'm so sorry you're dealing with that tooth pain").
    - partially followed: Mechanical, perfunctory acknowledgement.
    - not followed: Cold, indifferent, or robotic in the face of caller distress.
    - not possible to analyze: Purely transactional inquiry where empathy was not applicable.

E3. Use excessive fillers during the conversation?
    - Question: "use excessive fillers during the conversation?"
    - followed: Clean, polished speech with minimal or no verbal fillers ("um", "uh", "like").
    - partially followed: Occasional fillers that did not impede comprehension.
    - not followed: High frequency of fillers that compromised professionalism.
    - not possible to analyze: Automated transcript sanitized filler words.

E4. Display active listening skills?
    - Question: "display active listening skills?"
    - followed: Verified caller information, used verbal acknowledgements, avoided re-asking answered questions.
    - partially followed: Minor lapse (asked caller to repeat once).
    - not followed: Repeatedly ignored details or asked questions caller already answered.
    - not possible to analyze: Dialogue too short to determine.

E5. Interrupt the caller during the conversation?
    - Question: "interrupt the caller during the conversation?"
    - followed: Patiently allowed caller to complete thoughts without speaking over them.
    - partially followed: Single accidental overlap with immediate apology.
    - not followed: Blatantly talked over or cut off the caller repeatedly.
    - not possible to analyze: Turn-based transcript lacks acoustic overlap data (DEFAULT to this if no explicit interruption is evident in text).

E6. Was the Executive courteous with the caller during the call?
    - Question: "Was the Executive courteous with the caller during the call?"
    - followed: Consistently polite, respectful ("Please", "Thank you"), addressed caller respectfully.
    - partially followed: Mostly polite but slipped into overly blunt phrasing.
    - not followed: Impolite, condescending, or hostile tone.
    - not possible to analyze: Call too brief.

E7. Was the executive enthusiastic during the call? This includes intonation in the voice too
    - Question: "Was the executive enthusiastic during the call? This includes intonation in the voice too"
    - followed: Energetic, positive wording, welcoming engagement evident from dialogue phrasing.
    - partially followed: Flat or neutral but still polite.
    - not followed: Lethargic, bored, dismissive, or clearly disinterested.
    - not possible to analyze: Transcript cannot reliably convey acoustic pitch/energy (use if phrasing is neutral).

E8. Follow the protocol while placing the call on hold?
    - Question: "follow the protocol while placing the call on hold?"
    - followed: Asked permission, waited for consent, and thanked caller upon returning.
    - partially followed: Placed on hold without asking permission or forgot thank-you on return.
    - not followed: Put caller on hold abruptly or violated doctor-hold policy (trying to interrupt doctor in operatory).
    - not possible to analyze: Call was never placed on hold.

E9. Capture the caller's details accurately?
    - Question: "capture the caller's details accurately?"
    - followed: Recorded caller's name, phone, insurance, and clinical complaint without contradiction.
    - partially followed: Captured details with minor spelling or non-critical error.
    - not followed: Mixed up caller details or recorded contradictory information.
    - not possible to analyze: Information intake was not reached.

E10. Did the Executive comprehend what the caller was saying in the first instance?
    - Question: "Did the Executive comprehend what the caller was saying in the first instance?"
    - followed: Understood caller requests immediately and gave relevant responses on the first attempt.
    - partially followed: Needed 1 clarification or repetition.
    - not followed: Repeatedly misunderstood straightforward inquiries.
    - not possible to analyze: Call too short.

E11. Was the Executive able to explain himself well?
    - Question: "Was the Executive able to explain himself well?"
    - followed: Clear, articulate, structured, and easy-to-follow explanations.
    - partially followed: Slightly wordy or disjointed explanation.
    - not followed: Confusing, jargon-heavy, or unintelligible explanations.
    - not possible to analyze: Trainee spoke minimal words.

E12. Was the executive to the point and not wasted client minutes?
    - Question: "Was the executive to the point and not wasted client minutes?"
    - followed: Crisp, efficient, purpose-driven conversation that respected caller time.
    - partially followed: Minor rambling or hesitation but remained mostly on track.
    - not followed: Excessive padding, irrelevant chatter, or protracted confusion wasting caller minutes.
    - not possible to analyze: Call was cut short by external disconnect.

Return strictly valid JSON matching the schema with all 11 parameters audited.
"""


async def _execute_gemini_call(
    prompt: str,
    schema_cls: type,
    model_name: Optional[str] = None,
    http_timeout: Optional[float] = None,
    thinking_level: Optional[str] = None,
    stage_name: str = "Stage 1C",
) -> Tuple[Any, dict]:
    """Helper to execute structured JSON generation call to Gemini with rate-limit resiliency."""
    effective_thinking = thinking_level or getattr(settings, "GEMINI_THINKING_LEVEL_STAGE1C", "low")
    return await execute_gemini_structured_call(
        prompt=prompt,
        schema=schema_cls,
        stage_name=stage_name,
        thinking_level=effective_thinking,
        model_name=model_name,
        timeout=http_timeout,
    )


FALLBACK_QUESTIONS: Dict[str, str] = {
    "A1": "deliver a proper greeting that included his/her name and the name of the practice?",
    "A2": "offer to help the caller ?",
    "A3": "ask for the callers name and verify the number ?",
    "A4": "ask whether the caller is a new patient or not before scheduling the appointment in Dentrix, so that we can ask the patient to press 1 at the right time?",
    "B1": "probe the caller inorder to ascertain the nature of his/her query/issue?",
    "B2": "offer the appropriate solution to the caller?",
    "C1": "display adequate subject matter knowledge during the conversation?",
    "C2": "highlight the merits of the Doctor and the practice during the conversation?",
    "C3": "offer appropriate (upto 2 and no more) rebuttals for the objections raised by the caller?",
    "C4": "explain the rates, procedure & timings properly?",
    "C5": "volunteer to book an appointment for the caller during the conversation?",
    "D1": "paraphrase the caller's query/issue and the solution offered during the call?",
    "D2": "insist on the prospect sending the paperwork in advance during the conversation?",
    "D3": "check with the caller whether he/she had answered all of the queries before concluding the conversation ?",
    "D4": "wish the caller appropriately before concluding the conversation?",
    "E1": "express empathy over the caller's situation ?",
    "E2": "Was there Dead Air of more than 45s during the conversation ?",
    "E3": "use excessive fillers during the conversation?",
    "E4": "display active listening skills?",
    "E5": "interrupt the caller during the conversation?",
    "E6": "Was the Executive courteous with the caller during the call?",
    "E7": "Was the executive enthusiastic during the call? This includes intonation in the voice too",
    "E8": "follow the protocol while placing the call on hold?",
    "E9": "capture the caller's details accurately?",
    "E10": "Did the Executive comprehend what the caller was saying in the first instance?",
    "E11": "Was the Executive able to explain himself well?",
    "E12": "Was the executive to the point and not wasted client minutes?",
}


def _make_fallback_item(
    code: str,
    dead_air_triggered: Optional[bool] = None,
    error_msg: str = "Evaluation unavailable",
) -> VoiceRatingParameterItem:
    """Creates an individual parameter fallback item."""
    if code == "E2":
        if dead_air_triggered is True:
            return VoiceRatingParameterItem(
                code="E2",
                parameter_question=FALLBACK_QUESTIONS[code],
                verdict=VoiceVerdict.NOT_FOLLOWED,
                evidence_quote="Dead air episode >= 45.0s detected.",
                reasoning="Telemetry watchdog recorded prolonged silence exceeding 45 seconds.",
            )
        elif dead_air_triggered is False:
            return VoiceRatingParameterItem(
                code="E2",
                parameter_question=FALLBACK_QUESTIONS[code],
                verdict=VoiceVerdict.FOLLOWED,
                evidence_quote="No dead air >= 45.0s detected.",
                reasoning="Continuous conversational flow maintained without prolonged dead air exceeding 45 seconds.",
            )
        else:
            return VoiceRatingParameterItem(
                code="E2",
                parameter_question=FALLBACK_QUESTIONS[code],
                verdict=VoiceVerdict.NOT_POSSIBLE,
                evidence_quote="",
                reasoning="Audio timing telemetry unavailable.",
            )

    return VoiceRatingParameterItem(
        code=code,
        parameter_question=FALLBACK_QUESTIONS.get(code, ""),
        verdict=VoiceVerdict.NOT_POSSIBLE,
        evidence_quote="",
        reasoning=f"Automated evaluation unavailable: {error_msg}",
    )


def _create_fallback_response(
    dead_air_triggered: Optional[bool],
    error_msg: str,
) -> Tuple[VoiceRatingAuditResponse, dict]:
    """Generates a safe diagnostic fallback response when upstream LLM calls fail."""
    block_a = VoiceRatingSessionBlock.from_parameters("A", "Opening", [_make_fallback_item(c, error_msg=error_msg) for c in ("A1", "A2", "A3", "A4")])
    block_b = VoiceRatingSessionBlock.from_parameters("B", "Initial Addressal", [_make_fallback_item(c, error_msg=error_msg) for c in ("B1", "B2")])
    block_c = VoiceRatingSessionBlock.from_parameters("C", "Persuasion", [_make_fallback_item(c, error_msg=error_msg) for c in ("C1", "C2", "C3", "C4", "C5")])
    block_d = VoiceRatingSessionBlock.from_parameters("D", "Closure", [_make_fallback_item(c, error_msg=error_msg) for c in ("D1", "D2", "D3", "D4")])
    block_e = VoiceRatingSessionBlock.from_parameters("E", "Overall Communication", [_make_fallback_item(c, dead_air_triggered=dead_air_triggered, error_msg=error_msg) for c in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12")])

    resp = VoiceRatingAuditResponse.from_blocks(block_a, block_b, block_c, block_d, block_e)
    zero_usage = {
        "promptTokenCount": 0,
        "candidatesTokenCount": 0,
        "thoughtsTokenCount": 0,
        "totalTokenCount": 0,
    }
    return resp, zero_usage


async def audit_voice_rating_parameters(
    transcript: str,
    dead_air_triggered: Optional[bool] = None,
    model_name: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Tuple[VoiceRatingAuditResponse, dict]:
    """
    Executes Stage 1C Voice Rating Parameters evaluation.
    Dispatches 2 parallel sub-calls (Blocks A-D, and Block E) with sub-call isolation.
    Deterministically injects E2 from watchdog telemetry.
    """
    try:
        prompt_abcd = f"{SYSTEM_PROMPT_BLOCKS_ABCD}\n\n[CONVERSATION TRANSCRIPT TO AUDIT]:\n{transcript}"
        prompt_e = f"{SYSTEM_PROMPT_BLOCK_E}\n\n[CONVERSATION TRANSCRIPT TO AUDIT]:\n{transcript}"

        task_abcd = _execute_gemini_call(
            prompt_abcd,
            Stage1CBlocksABCDRawResponse,
            model_name=model_name,
            http_timeout=timeout,
            stage_name="Stage 1C Sub-call 1 (Blocks A-D)",
        )
        task_e = _execute_gemini_call(
            prompt_e,
            Stage1CBlockERawResponse,
            model_name=model_name,
            http_timeout=timeout,
            stage_name="Stage 1C Sub-call 2 (Block E)",
        )

        results = await asyncio.gather(task_abcd, task_e, return_exceptions=True)
        res_abcd, res_e = results[0], results[1]

        # Process Sub-call 1 (Blocks A-D) with isolation
        usage_abcd = {}
        if isinstance(res_abcd, Exception):
            logger.warning(f"Stage 1C Sub-call 1 (Blocks A-D) failed: {res_abcd}. Generating fallback for A-D.")
            err_abcd = str(res_abcd)
            params_a = [_make_fallback_item(c, error_msg=err_abcd) for c in ("A1", "A2", "A3", "A4")]
            params_b = [_make_fallback_item(c, error_msg=err_abcd) for c in ("B1", "B2")]
            params_c = [_make_fallback_item(c, error_msg=err_abcd) for c in ("C1", "C2", "C3", "C4", "C5")]
            params_d = [_make_fallback_item(c, error_msg=err_abcd) for c in ("D1", "D2", "D3", "D4")]
        else:
            raw_abcd, usage_abcd = res_abcd
            params_a = raw_abcd.session_a_parameters
            params_b = raw_abcd.session_b_parameters
            params_c = raw_abcd.session_c_parameters
            params_d = raw_abcd.session_d_parameters

        block_a = VoiceRatingSessionBlock.from_parameters("A", "Opening", params_a)
        block_b = VoiceRatingSessionBlock.from_parameters("B", "Initial Addressal", params_b)
        block_c = VoiceRatingSessionBlock.from_parameters("C", "Persuasion", params_c)
        block_d = VoiceRatingSessionBlock.from_parameters("D", "Closure", params_d)

        # Process Sub-call 2 (Block E) with deterministic E2 injection and isolation
        usage_e = {}
        e2_item = _make_fallback_item("E2", dead_air_triggered=dead_air_triggered)

        if isinstance(res_e, Exception):
            logger.warning(f"Stage 1C Sub-call 2 (Block E) failed: {res_e}. Generating fallback for E.")
            err_e = str(res_e)
            e_params = []
            for c in ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12"):
                if c == "E2":
                    e_params.append(e2_item)
                else:
                    e_params.append(_make_fallback_item(c, error_msg=err_e))
        else:
            raw_e, usage_e = res_e
            e_params = []
            e2_inserted = False
            for p in raw_e.session_e_parameters:
                code_upper = (p.code or "").upper().strip()
                if not e2_inserted and code_upper in ("E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E11", "E12"):
                    e_params.append(e2_item)
                    e2_inserted = True
                if code_upper != "E2":
                    e_params.append(p)
            if not e2_inserted:
                e_params.append(e2_item)

        block_e = VoiceRatingSessionBlock.from_parameters("E", "Overall Communication", e_params)

        # Assemble consolidated response
        consolidated_response = VoiceRatingAuditResponse.from_blocks(
            block_a=block_a,
            block_b=block_b,
            block_c=block_c,
            block_d=block_d,
            block_e=block_e,
        )

        combined_usage = {
            "promptTokenCount": usage_abcd.get("promptTokenCount", 0) + usage_e.get("promptTokenCount", 0),
            "candidatesTokenCount": usage_abcd.get("candidatesTokenCount", 0) + usage_e.get("candidatesTokenCount", 0),
            "thoughtsTokenCount": usage_abcd.get("thoughtsTokenCount", 0) + usage_e.get("thoughtsTokenCount", 0),
            "totalTokenCount": usage_abcd.get("totalTokenCount", 0) + usage_e.get("totalTokenCount", 0),
        }

        return consolidated_response, combined_usage

    except Exception as exc:
        logger.error(
            f"Stage 1C Voice Rating Auditor encountered an error: {exc}. Generating resilient diagnostic fallback.",
            exc_info=True,
        )
        return _create_fallback_response(dead_air_triggered, error_msg=str(exc))
