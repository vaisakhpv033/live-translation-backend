"""
Master Pipeline Orchestrator for Dental QA Engine
Executes Stage 1A & 1B in parallel, followed by Stage 2 and Stage 3.
Synchronizes deterministic math with qualitative coaching narrative.
"""

import asyncio
import logging
from typing import Optional

from app.modules.dental_qa.schemas import (
    CallMetadata,
    QualitativeAnalysis,
    DentalQAReportCard,
)
from .stage1a_sop_auditor import audit_dental_sops
from .stage1b_clinic_auditor import audit_clinic_protocols
from .stage2_behavioral_evaluator import evaluate_behavioral_dimensions
from .stage3_scoring_engine import calculate_clamped_scores, DEFAULT_WEIGHTS

logger = logging.getLogger("dental_qa_engine.orchestrator")


async def evaluate_dental_call(
    transcript: str,
    metadata: Optional[CallMetadata] = None,
    weights: Optional[dict] = None,
    model_name: Optional[str] = None,
) -> DentalQAReportCard:
    """
    Runs the complete 2-Stage Multi-Call evaluation pipeline:
    1. Parallel execution: Stage 1A (SOP Audit) & Stage 1B (Clinic Audit)
    2. Sequential execution: Stage 2 (Holistic Behavioral Evaluator)
    3. Deterministic execution: Stage 3 (Python Math & Clamping Engine)
    """
    call_meta = metadata or CallMetadata(job_id="job_live_simulation")

    logger.info(f"Starting 2-Stage Multi-Call QA Evaluation for job: {call_meta.job_id}")

    # STAGE 1: Parallel Execution of SOP and Clinic Audits
    logger.info("Dispatching Stage 1A & 1B in parallel...")
    sop_task = audit_dental_sops(transcript, model_name=model_name)
    clinic_task = audit_clinic_protocols(transcript, model_name=model_name)

    (sop_res, sop_usage), (clinic_res, clinic_usage) = await asyncio.gather(sop_task, clinic_task)
    logger.info(
        f"Stage 1 Complete. SOP Triggers: {len(sop_res.sop_audit_table)}, "
        f"Clinic Triggers: {len(clinic_res.clinic_audit_table)}"
    )

    # STAGE 2: Behavioral & Qualitative Evaluation
    logger.info("Dispatching Stage 2 Behavioral Evaluator...")
    behavioral_res, behavioral_usage = await evaluate_behavioral_dimensions(
        transcript=transcript,
        sop_audits=sop_res.sop_audit_table,
        clinic_audits=clinic_res.clinic_audit_table,
        model_name=model_name,
    )
    logger.info("Stage 2 Behavioral Evaluation Complete.")

    # Collect raw scores from Stage 1 & Stage 2
    raw_scores = {
        "dental_sop_adherence": sop_res.dental_sop_adherence_score,
        "clinic_protocol_adherence": clinic_res.clinic_protocol_adherence_score,
        "rapport_professionalism": behavioral_res.rapport_professionalism.score,
        "discovery_needs_analysis": behavioral_res.discovery_needs_analysis.score,
        "communication_skills": behavioral_res.communication_skills.score,
        "objection_handling": behavioral_res.objection_handling.score,
        "recommendation_quality": behavioral_res.recommendation_quality.score,
        "compliance_ethical_conduct": behavioral_res.compliance_ethical_conduct.score,
        "closing_effectiveness": behavioral_res.closing_effectiveness.score,
    }

    # STAGE 3: Deterministic Clamping & Programmatic Weighted Calculation
    logger.info("Executing Stage 3 Deterministic Scoring Engine...")
    evaluated_scores = calculate_clamped_scores(
        raw_scores=raw_scores,
        sop_audits=sop_res.sop_audit_table,
        clinic_audits=clinic_res.clinic_audit_table,
        weights=weights or DEFAULT_WEIGHTS,
    )
    logger.info(
        f"Stage 3 Complete. Overall Score: {evaluated_scores.overall_score}/100 "
        f"({evaluated_scores.readiness_assessment})"
    )

    # Harmonize Stage 2 narrative with Stage 3 deterministic math
    clamp_explanation = (
        " [Mandatory penalty clamping was enforced due to critical protocol violations.]"
        if evaluated_scores.clamping_applied
        else ""
    )
    authoritative_justification = (
        f"Overall Assessment: {evaluated_scores.overall_score}/100 ({evaluated_scores.readiness_assessment})."
        f"{clamp_explanation}\n\n"
        f"{behavioral_res.assessment_reasoning_justification}"
    )

    # Assemble Final Report Card
    qualitative_analysis = QualitativeAnalysis(
        call_summary=behavioral_res.call_summary,
        dental_sop_verbiage_audits=sop_res.sop_audit_table,
        clinic_protocol_audits=clinic_res.clinic_audit_table,
        strengths=behavioral_res.strengths,
        improvement_opportunities=behavioral_res.improvement_opportunities,
        missed_opportunities=behavioral_res.missed_opportunities,
        compliance_review_security=behavioral_res.compliance_review_security,
        coaching_recommendations=behavioral_res.coaching_recommendations,
        assessment_reasoning_justification=authoritative_justification,
    )

    # Aggregate token metrics & costs across all 3 Gemini calls
    p_tokens = (
        sop_usage.get("promptTokenCount", 0)
        + clinic_usage.get("promptTokenCount", 0)
        + behavioral_usage.get("promptTokenCount", 0)
    )
    c_tokens = (
        sop_usage.get("candidatesTokenCount", 0)
        + clinic_usage.get("candidatesTokenCount", 0)
        + behavioral_usage.get("candidatesTokenCount", 0)
    )
    t_tokens = (
        sop_usage.get("thoughtsTokenCount", 0)
        + clinic_usage.get("thoughtsTokenCount", 0)
        + behavioral_usage.get("thoughtsTokenCount", 0)
    )
    cost_usd = round(
        ((p_tokens / 1_000_000.0) * 0.75) + (((c_tokens + t_tokens) / 1_000_000.0) * 3.75), 6
    )

    token_usage_dict = {
        "prompt_tokens": p_tokens,
        "candidates_tokens": c_tokens,
        "thoughts_tokens": t_tokens,
        "total_tokens": p_tokens + c_tokens + t_tokens,
        "total_cost_usd": cost_usd,
    }

    return DentalQAReportCard(
        call_metadata=call_meta,
        scores=evaluated_scores,
        detailed_analysis=qualitative_analysis,
        token_usage=token_usage_dict,
    )

