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
    EvaluatedScores,
    QualitativeAnalysis,
    DentalQAReportCard,
    ComplianceSecurityReview,
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

    Guards against empty/absent transcripts: returns a zeroed report card immediately
    without making any LLM calls.
    """
    call_meta = metadata or CallMetadata(job_id="job_live_simulation")

    # Guard: Detect empty or absent conversation transcript
    cleaned_transcript = (transcript or "").strip()
    if not cleaned_transcript or cleaned_transcript.lower() in {
        "no transcript available.",
        "no transcript available",
        "no dialogue recorded in transcript.",
        "no dialogue recorded in transcript",
        "[]",
        "{}",
    }:
        logger.warning(
            f"No conversation dialogue in transcript for job: {call_meta.job_id}. "
            "Skipping LLM evaluation calls and generating zeroed evaluation card."
        )
        no_data_reason = "No call data recorded. Evaluation cannot be performed because no conversation occurred."
        return DentalQAReportCard(
            call_metadata=call_meta,
            scores=EvaluatedScores(
                rapport_professionalism=0,
                discovery_needs_analysis=0,
                dental_sop_adherence=0,
                communication_skills=0,
                objection_handling=0,
                recommendation_quality=0,
                compliance_ethical_conduct=0,
                closing_effectiveness=0,
                clinic_protocol_adherence=0,
                overall_score=0,
                readiness_assessment="Not Ready",
                clamping_applied=False,
            ),
            detailed_analysis=QualitativeAnalysis(
                call_summary="No call data recorded. Call was disconnected or no conversation occurred, so evaluation cannot be done.",
                dental_sop_verbiage_audits=[],
                clinic_protocol_audits=[],
                strengths=[],
                improvement_opportunities=["Ensure audio and microphone are connected so dialogue can be recorded."],
                missed_opportunities=[],
                compliance_review_security=ComplianceSecurityReview(
                    pci_dss_prepayment="Not evaluated: No call data recorded.",
                    hipaa_privacy="Not evaluated: No call data recorded.",
                    security_credentials="Not evaluated: No call data recorded.",
                ),
                coaching_recommendations=["Perform a test call to verify microphone audio before starting simulation."],
                assessment_reasoning_justification="No call data available. The session contained no dialogue or audio transcript, so performance could not be evaluated.",
                dimension_explanations={
                    "rapport": no_data_reason,
                    "discovery": no_data_reason,
                    "sop_adherence": no_data_reason,
                    "communication": no_data_reason,
                    "objection_handling": no_data_reason,
                    "recommendation_quality": no_data_reason,
                    "compliance": no_data_reason,
                    "closing": no_data_reason,
                    "clinic_protocol_adherence": no_data_reason,
                },
            ),
            token_usage={
                "prompt_tokens": 0,
                "candidates_tokens": 0,
                "thoughts_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            },
        )

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

    # Map dynamic, evidence-based reasoning from Stage 1 & Stage 2 evaluators
    dimension_explanations = {
        "rapport": behavioral_res.rapport_professionalism.reason,
        "discovery": behavioral_res.discovery_needs_analysis.reason,
        "sop_adherence": sop_res.dental_sop_adherence_reason,
        "communication": behavioral_res.communication_skills.reason,
        "objection_handling": behavioral_res.objection_handling.reason,
        "recommendation_quality": behavioral_res.recommendation_quality.reason,
        "compliance": behavioral_res.compliance_ethical_conduct.reason,
        "closing": behavioral_res.closing_effectiveness.reason,
        "clinic_protocol_adherence": clinic_res.clinic_protocol_adherence_reason,
    }

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
        dimension_explanations=dimension_explanations,
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

