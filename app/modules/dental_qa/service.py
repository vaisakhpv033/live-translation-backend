"""
Dental QA Service Layer
Bridges LiveKit call telemetries, runs the 2-Stage Multi-Call evaluation pipeline,
formats backward-compatible payloads for frontend UIs, and persists structured audits in PostgreSQL.
"""

from __future__ import annotations
import json
import uuid
import logging
from datetime import datetime, UTC
from typing import Optional, Tuple, Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.modules.dental_qa.core.orchestrator import evaluate_dental_call
from app.modules.dental_qa.schemas import (
    CallMetadata,
    DentalQAReportCard,
)
from app.modules.dental_qa.models import DentalCallEvaluation

logger = logging.getLogger("translation-agent-backend.modules.dental_qa.service")


class DentalQAService:
    """
    High-level facade service for the Dental QA Evaluation Engine.
    Handles transcript normalization, orchestrator execution, frontend payload mapping,
    and PostgreSQL persistence.
    """

    @staticmethod
    def format_transcript(chat_history_str: Optional[str]) -> str:
        """
        Parses LiveKit chat history (JSON or list) into a clean, speaker-attributed dialogue transcript.
        Maps speakers into:
        - 'Front Desk Trainee' (trainee / student / agent / user depending on livekit role tagging)
        - 'Patient' (caller / customer / simulator)
        """
        if not chat_history_str:
            return "No transcript available."

        # If it's already plain text (e.g. from benchmark or unit test), return as-is
        trimmed = chat_history_str.strip()
        if not (trimmed.startswith("{") or trimmed.startswith("[")):
            return trimmed

        try:
            data = json.loads(trimmed)
            items: List[Dict[str, Any]] = []
            if isinstance(data, dict):
                items = data.get("items", [])
            elif isinstance(data, list):
                items = data

            lines: List[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if "type" in item and item.get("type") != "message":
                    continue

                role = (item.get("role") or "").lower()
                if role == "system":
                    continue

                content_val = item.get("content")
                text = ""
                if isinstance(content_val, list) and content_val:
                    text = " ".join([str(c) for c in content_val if isinstance(c, str)])
                elif isinstance(content_val, str) and content_val.strip():
                    text = content_val.strip()

                if not text:
                    for fallback_key in ["text", "message", "transcript"]:
                        val = item.get(fallback_key)
                        if isinstance(val, str) and val.strip():
                            text = val.strip()
                            break

                text = text.strip()
                if not text:
                    continue

                # Role attribution: Trainee vs Patient
                if role in ["user", "trainee", "human", "agent"]:
                    speaker = "Front Desk Trainee"
                else:
                    speaker = "Patient"

                lines.append(f"{speaker}: {text}")

            return "\n".join(lines) if lines else "No dialogue recorded in transcript."

        except Exception as e:
            logger.warning(f"Error parsing chat history JSON for dental transcript: {e}")
            return chat_history_str

    async def evaluate_transcript_payload(
        self,
        chat_history_str: Optional[str],
        scenario: Optional[str] = "dental_scheduling",
        job_id: Optional[str] = None,
        patient_name: Optional[str] = None,
        trainee_name: Optional[str] = None,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        Executes the 2-Stage Multi-Call evaluation pipeline and returns
        (frontend_report_card_dict, overall_score).
        """
        transcript = self.format_transcript(chat_history_str)
        if not transcript or transcript == "No transcript available.":
            logger.warning(f"Empty transcript for job {job_id}; evaluation aborted.")
            return None, 0

        metadata = CallMetadata(
            job_id=job_id or f"job_{uuid.uuid4().hex[:8]}",
            patient_name=patient_name or "Dental Patient",
            trainee_name=trainee_name or "Front Desk Trainee",
            clinic_name="Citrus Smiles Dental",
            lead_provider="Dr. Mahima Gupta",
        )

        try:
            report_card: DentalQAReportCard = await evaluate_dental_call(
                transcript=transcript,
                metadata=metadata,
            )

            # Build harmonized frontend payload
            frontend_payload = self.to_frontend_payload(report_card, scenario=scenario or "dental_scheduling")
            return frontend_payload, report_card.scores.overall_score

        except Exception as e:
            logger.exception(f"Unhandled exception during dental QA evaluation for job {job_id}: {e}")
            return None, 0

    def to_frontend_payload(
        self, report_card: DentalQAReportCard, scenario: str = "dental_scheduling"
    ) -> Dict[str, Any]:
        """
        Maps DentalQAReportCard into the exact contract expected by AutoCoach/Frontend
        while exposing all new 2-Stage Multi-Call audit tables and clinic metrics.
        """
        scores = report_card.scores
        details = report_card.detailed_analysis

        # Collect compliance violations across both tables
        compliance_issues: List[str] = []
        for c in details.clinic_protocol_audits:
            if (c.verdict or "").strip().lower() == "violated":
                compliance_issues.append(f"Clinic Rule Breach [{c.rule_id}]: {c.violation_details}")
        for s in details.dental_sop_verbiage_audits:
            if (s.verdict or "").strip().lower() == "violated":
                compliance_issues.append(f"SOP Violation [{s.sop_id}]: {s.violation_details}")

        # Synthesize overall SOP adherence verdict
        has_critical_fail = scores.clamping_applied or any(
            (c.verdict or "").strip().lower() == "violated" for c in details.clinic_protocol_audits
        ) or any(
            (s.verdict or "").strip().lower() == "violated" for s in details.dental_sop_verbiage_audits
        )
        if scores.overall_score >= 80 and not has_critical_fail:
            overall_verdict = "Fully Compliant"
        elif scores.overall_score >= 50:
            overall_verdict = "Partially Compliant"
        else:
            overall_verdict = "Non-Compliant"

        sop_adherence_summary: Dict[str, Any] = {
            "overall_sop_verdict": overall_verdict,
            "sop_violations_count": sum(1 for s in details.dental_sop_verbiage_audits if (s.verdict or "").strip().lower() == "violated"),
            "clinic_violations_count": sum(1 for c in details.clinic_protocol_audits if (c.verdict or "").strip().lower() == "violated"),
        }

        # Frontend ReportCard structure matching DentalReportCard in reportService.ts
        payload: Dict[str, Any] = {
            "scenario_practiced": details.call_summary or f"Citrus Smiles Dental Simulation ({scenario})",
            "overall_score": scores.overall_score,

            # 8 Core Criteria (1-10) with explanations
            "rapport": {
                "score": scores.rapport_professionalism,
                "reason": "Warm greeting, empathy, identifying self & practice, patient comfort.",
            },
            "discovery": {
                "score": scores.discovery_needs_analysis,
                "reason": "Diagnostic inquiry into dental pain, symptoms, affected teeth, and history.",
            },
            "sop_adherence": {
                "score": scores.dental_sop_adherence,
                "reason": f"Audit of 41 standard dental front-desk objection verbiages. Verdict: {overall_verdict}.",
            },
            "communication": {
                "score": scores.communication_skills,
                "reason": "Clarity, active listening, conversational pacing, jargon-free explanations.",
            },
            "objection_handling": {
                "score": scores.objection_handling,
                "reason": "Managing pricing, doctor availability, and appointment friction with empathy.",
            },
            "recommendation_quality": {
                "score": scores.recommendation_quality,
                "reason": "Appropriate clinical scheduling, exam/scan recommendations, emergency prioritization.",
            },
            "compliance": {
                "score": scores.compliance_ethical_conduct,
                "reason": "HIPAA compliance, no medical diagnoses over phone, PCI-DSS prepayment adherence.",
            },
            "closing": {
                "score": scores.closing_effectiveness,
                "reason": "Confirming appointment time, doctor, landmarks, cancellation policy, warm closing.",
            },

            # New Metric: Clinic Protocol Adherence (Citrus Smiles specific)
            "clinic_protocol_adherence": {
                "score": scores.clinic_protocol_adherence,
                "reason": "Strict compliance with Citrus Smiles operating days, lead provider, and payment policies.",
            },

            # Qualitative Lists
            "positives": details.strengths,
            "improvement_areas": details.improvement_opportunities,
            "missed_opportunities": details.missed_opportunities,
            "compliance_issues": compliance_issues,
            "coaching_recommendations": details.coaching_recommendations,
            "compliance_review_security": details.compliance_review_security.model_dump(),

            # Readiness Tier & Narrative
            "readiness_assessment": scores.readiness_assessment,
            "readiness_reasoning": details.assessment_reasoning_justification,

            # Audit Tables
            "sop_audit_table": [item.model_dump() for item in details.dental_sop_verbiage_audits],
            "clinic_audit_table": [item.model_dump() for item in details.clinic_protocol_audits],
            "clamping_applied": scores.clamping_applied,
            "sop_adherence_summary": sop_adherence_summary,

            # Call metadata
            "call_metadata": report_card.call_metadata.model_dump(),
            "token_usage": report_card.token_usage,
        }

        return payload

    async def persist_dental_evaluation(
        self,
        session: AsyncSession,
        job_id: str,
        report_card_payload: Dict[str, Any],
        token_usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Upserts the granular evaluation into the dedicated `dental_evaluations` table.
        """
        try:
            tokens = token_usage or report_card_payload.get("token_usage") or {}
            now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")

            scores_dict = report_card_payload
            safe_job_id = job_id or f"job_{uuid.uuid4().hex[:8]}"
            eval_id = f"deval_{safe_job_id}"

            stmt = pg_insert(DentalCallEvaluation).values(
                id=eval_id,
                job_id=safe_job_id,
                overall_score=scores_dict.get("overall_score", 0),
                clamping_applied=scores_dict.get("clamping_applied", False),
                readiness_assessment=scores_dict.get("readiness_assessment", "Developing"),

                rapport_score=scores_dict.get("rapport", {}).get("score", 5),
                discovery_score=scores_dict.get("discovery", {}).get("score", 5),
                dental_sop_score=scores_dict.get("sop_adherence", {}).get("score", 5),
                clinic_protocol_score=scores_dict.get("clinic_protocol_adherence", {}).get("score", 5),
                communication_score=scores_dict.get("communication", {}).get("score", 5),
                objection_handling_score=scores_dict.get("objection_handling", {}).get("score", 5),
                recommendation_quality_score=scores_dict.get("recommendation_quality", {}).get("score", 5),
                compliance_score=scores_dict.get("compliance", {}).get("score", 5),
                closing_score=scores_dict.get("closing", {}).get("score", 5),

                call_summary=scores_dict.get("scenario_practiced"),
                sop_audit_table=json.dumps(scores_dict.get("sop_audit_table", [])),
                clinic_audit_table=json.dumps(scores_dict.get("clinic_audit_table", [])),
                strengths=json.dumps(scores_dict.get("positives", [])),
                improvement_opportunities=json.dumps(scores_dict.get("improvement_areas", [])),
                missed_opportunities=json.dumps(scores_dict.get("missed_opportunities", [])),
                coaching_recommendations=json.dumps(scores_dict.get("coaching_recommendations", [])),
                compliance_review_security=json.dumps(scores_dict.get("compliance_review_security", {})),
                assessment_reasoning_justification=scores_dict.get("readiness_reasoning"),

                total_prompt_tokens=tokens.get("prompt_tokens", 0),
                total_candidates_tokens=tokens.get("candidates_tokens", 0),
                total_thoughts_tokens=tokens.get("thoughts_tokens", 0),
                estimated_cost_usd=tokens.get("total_cost_usd", 0.0),
                created_at=now_iso,
            )

            # On conflict with same id, update record
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "overall_score": stmt.excluded.overall_score,
                    "clamping_applied": stmt.excluded.clamping_applied,
                    "readiness_assessment": stmt.excluded.readiness_assessment,
                    "rapport_score": stmt.excluded.rapport_score,
                    "discovery_score": stmt.excluded.discovery_score,
                    "dental_sop_score": stmt.excluded.dental_sop_score,
                    "clinic_protocol_score": stmt.excluded.clinic_protocol_score,
                    "communication_score": stmt.excluded.communication_score,
                    "objection_handling_score": stmt.excluded.objection_handling_score,
                    "recommendation_quality_score": stmt.excluded.recommendation_quality_score,
                    "compliance_score": stmt.excluded.compliance_score,
                    "closing_score": stmt.excluded.closing_score,
                    "call_summary": stmt.excluded.call_summary,
                    "sop_audit_table": stmt.excluded.sop_audit_table,
                    "clinic_audit_table": stmt.excluded.clinic_audit_table,
                    "strengths": stmt.excluded.strengths,
                    "improvement_opportunities": stmt.excluded.improvement_opportunities,
                    "missed_opportunities": stmt.excluded.missed_opportunities,
                    "coaching_recommendations": stmt.excluded.coaching_recommendations,
                    "compliance_review_security": stmt.excluded.compliance_review_security,
                    "assessment_reasoning_justification": stmt.excluded.assessment_reasoning_justification,
                    "total_prompt_tokens": stmt.excluded.total_prompt_tokens,
                    "total_candidates_tokens": stmt.excluded.total_candidates_tokens,
                    "total_thoughts_tokens": stmt.excluded.total_thoughts_tokens,
                    "estimated_cost_usd": stmt.excluded.estimated_cost_usd,
                    "created_at": stmt.excluded.created_at,
                }
            )

            await session.execute(stmt)
            logger.info(f"Persisted structured dental evaluation for job {job_id} into dental_evaluations table.")

        except Exception as e:
            logger.exception(f"Failed to persist structured dental evaluation for job {job_id}: {e}")


# Singleton instance accessor
_dental_qa_service: Optional[DentalQAService] = None

def get_dental_qa_service() -> DentalQAService:
    global _dental_qa_service
    if _dental_qa_service is None:
        _dental_qa_service = DentalQAService()
    return _dental_qa_service

