"""Async PostgreSQL repository for USV Doctor Detailing reports and usage metrics."""

import logging
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.usv_doctor.models import UsvDoctorReport

logger = logging.getLogger("translation-agent-backend.modules.usv_doctor.repository")


class UsvDoctorReportRepository:
    """Data access layer for the `usv_doctor_reports` table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_initial_report(self, report_data: Dict[str, Any]) -> None:
        """Upserts an incoming post-call webhook report and AutoCoach usage metrics."""
        job_id = report_data["job_id"]
        logger.info(f"Saving USV Doctor report for job: {job_id}")

        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        values = {
            **report_data,
            "created_at": report_data.get("created_at") or now_iso,
        }

        stmt = pg_insert(UsvDoctorReport).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in values.keys() if k != "job_id"}
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_id"],
            set_=update_cols,
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_by_job_id(self, job_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(UsvDoctorReport).where(UsvDoctorReport.job_id == job_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._row_to_dict(row) if row else None

    async def get_all(self) -> List[Dict[str, Any]]:
        stmt = select(UsvDoctorReport).order_by(UsvDoctorReport.ended_at.desc())
        result = await self.session.execute(stmt)
        return [self._row_to_dict(row) for row in result.scalars().all()]

    async def get_ongoing_reports(self) -> List[Dict[str, Any]]:
        stmt = select(UsvDoctorReport).where(UsvDoctorReport.status == "ongoing")
        result = await self.session.execute(stmt)
        return [self._row_to_dict(row) for row in result.scalars().all()]

    async def update_evaluation(
        self,
        job_id: str,
        summary: Optional[str],
        overall_score: int,
        readiness_assessment: Optional[str],
        status: str,
        qa_model_name: Optional[str] = None,
        qa_usage_metadata: Optional[str] = None,
        qa_prompt_tokens: int = 0,
        qa_cached_tokens: int = 0,
        qa_candidates_tokens: int = 0,
        qa_thoughts_tokens: int = 0,
        qa_total_tokens: int = 0,
        qa_cost_usd: float = 0.0,
        total_cost_usd: Optional[float] = None,
    ) -> None:
        stmt = select(UsvDoctorReport).where(UsvDoctorReport.job_id == job_id)
        result = await self.session.execute(stmt)
        report = result.scalar_one_or_none()
        if not report:
            logger.warning(f"Cannot update evaluation: USV Doctor report '{job_id}' not found.")
            return

        report.summary = summary
        report.overall_score = overall_score
        report.readiness_assessment = readiness_assessment
        report.status = status
        report.qa_model_name = qa_model_name
        report.qa_usage_metadata = qa_usage_metadata
        report.qa_prompt_tokens = qa_prompt_tokens
        report.qa_cached_tokens = qa_cached_tokens
        report.qa_candidates_tokens = qa_candidates_tokens
        report.qa_thoughts_tokens = qa_thoughts_tokens
        report.qa_total_tokens = qa_total_tokens
        report.qa_cost_usd = qa_cost_usd
        if total_cost_usd is not None:
            report.total_cost_usd = total_cost_usd
        else:
            report.total_cost_usd = round(float(report.agent_cost_usd or 0.0) + float(qa_cost_usd or 0.0), 6)

    async def reset_for_retry(self, job_id: str) -> Optional[Dict[str, Any]]:
        stmt = select(UsvDoctorReport).where(UsvDoctorReport.job_id == job_id)
        result = await self.session.execute(stmt)
        report = result.scalar_one_or_none()
        if not report:
            return None

        report.summary = None
        report.overall_score = 0
        report.readiness_assessment = None
        report.status = "ongoing"
        report.qa_usage_metadata = None
        report.qa_prompt_tokens = 0
        report.qa_cached_tokens = 0
        report.qa_candidates_tokens = 0
        report.qa_thoughts_tokens = 0
        report.qa_total_tokens = 0
        report.qa_cost_usd = 0.0
        report.total_cost_usd = float(report.agent_cost_usd or 0.0)
        await self.session.commit()
        return self._row_to_dict(report)

    @staticmethod
    def _row_to_dict(row: UsvDoctorReport) -> Dict[str, Any]:
        return {
            "job_id": row.job_id,
            "session_id": row.session_id,
            "room_name": row.room_name,
            "agent_name": row.agent_name,
            "agent_role": row.agent_role,
            "started_at": row.started_at,
            "ended_at": row.ended_at,
            "duration_seconds": row.duration_seconds,
            "termination_reason": row.termination_reason,
            "error_info": row.error_info,
            "status": row.status,
            "created_at": row.created_at,
            "scenario": row.scenario,
            "scenario_id": row.scenario_id,
            "title": row.title,
            "doctor_name": row.doctor_name,
            "doctor_specialty": row.doctor_specialty,
            "clinic_setting": row.clinic_setting,
            "demeanor": row.demeanor,
            "trainee_name": row.trainee_name,
            "trainee_id": row.trainee_id,
            "model_name": row.model_name,
            "language": row.language,
            "voice_id": row.voice_id,
            "session_metadata": row.session_metadata,
            "chat_history": row.chat_history,
            "events": row.events,
            "audio_recording_path": row.audio_recording_path,
            "summary": row.summary,
            "overall_score": row.overall_score,
            "readiness_assessment": row.readiness_assessment,
            "agent_model_usage": row.agent_model_usage,
            "agent_input_tokens": row.agent_input_tokens,
            "agent_input_cached_tokens": row.agent_input_cached_tokens,
            "agent_input_text_tokens": row.agent_input_text_tokens,
            "agent_input_audio_tokens": row.agent_input_audio_tokens,
            "agent_output_tokens": row.agent_output_tokens,
            "agent_output_text_tokens": row.agent_output_text_tokens,
            "agent_output_audio_tokens": row.agent_output_audio_tokens,
            "agent_reasoning_tokens": row.agent_reasoning_tokens,
            "agent_total_tokens": row.agent_total_tokens,
            "agent_cost_usd": row.agent_cost_usd,
            "qa_usage_metadata": row.qa_usage_metadata,
            "qa_model_name": row.qa_model_name,
            "qa_prompt_tokens": row.qa_prompt_tokens,
            "qa_cached_tokens": row.qa_cached_tokens,
            "qa_candidates_tokens": row.qa_candidates_tokens,
            "qa_thoughts_tokens": row.qa_thoughts_tokens,
            "qa_total_tokens": row.qa_total_tokens,
            "qa_cost_usd": row.qa_cost_usd,
            "total_cost_usd": row.total_cost_usd,
        }
