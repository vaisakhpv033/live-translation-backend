import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.report import Report

logger = logging.getLogger("translation-agent-backend.repositories.report")


class IReportRepository(ABC):
    """
    Interface for report data access operations (Interface Segregation).
    """
    @abstractmethod
    async def save(self, report_data: dict) -> None:
        """Upserts a report record."""
        pass

    @abstractmethod
    async def get_by_job_id(self, job_id: str) -> Optional[dict]:
        """Retrieves a single report by job_id."""
        pass

    @abstractmethod
    async def get_all(self) -> List[dict]:
        """Retrieves all reports ordered by ended_at descending."""
        pass

    @abstractmethod
    async def get_ongoing_reports(self) -> List[dict]:
        """Retrieves all reports with status = 'ongoing'."""
        pass

    @abstractmethod
    async def update_summary(
        self, job_id: str, summary: Optional[str], overall_score: int, status: str
    ) -> None:
        """Updates the evaluation summary, score, and status for a report."""
        pass


class SQLAlchemyReportRepository(IReportRepository):
    """
    SQLAlchemy async implementation of IReportRepository (Dependency Inversion).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, report_data: dict) -> None:
        """
        Upserts a report using PostgreSQL ON CONFLICT DO UPDATE.
        """
        logger.info(f"Saving report: {report_data.get('job_id')}")

        # Calculate duration if not provided
        duration = report_data.get("duration_seconds")
        if duration is None:
            started_at = report_data.get("started_at")
            ended_at = report_data.get("ended_at")
            if started_at and ended_at:
                duration = self._compute_duration(started_at, ended_at)
            else:
                duration = 0

        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        stmt = pg_insert(Report).values(
            job_id=report_data["job_id"],
            room_id=report_data.get("room_id"),
            room=report_data.get("room"),
            started_at=report_data.get("started_at"),
            ended_at=report_data.get("ended_at"),
            duration_seconds=duration,
            summary=report_data.get("summary"),
            overall_score=report_data.get("overall_score", 0),
            chat_history=report_data.get("chat_history"),
            status=report_data.get("status", "ongoing"),
            customer_name=report_data.get("customer_name"),
            agent_type=report_data.get("agent_type"),
            sales_rep=report_data.get("sales_rep"),
            scenario=report_data.get("scenario", "sbi"),
            created_at=now_iso,
        )

        # On conflict (job_id already exists), update all fields
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_id"],
            set_={
                "room_id": stmt.excluded.room_id,
                "room": stmt.excluded.room,
                "started_at": stmt.excluded.started_at,
                "ended_at": stmt.excluded.ended_at,
                "duration_seconds": stmt.excluded.duration_seconds,
                "summary": stmt.excluded.summary,
                "overall_score": stmt.excluded.overall_score,
                "chat_history": stmt.excluded.chat_history,
                "status": stmt.excluded.status,
                "customer_name": stmt.excluded.customer_name,
                "agent_type": stmt.excluded.agent_type,
                "sales_rep": stmt.excluded.sales_rep,
                "scenario": stmt.excluded.scenario,
                "created_at": stmt.excluded.created_at,
            }
        )

        await self.session.execute(stmt)
        await self.session.commit()

    async def get_by_job_id(self, job_id: str) -> Optional[dict]:
        logger.info(f"Fetching report: {job_id}")
        stmt = select(Report).where(Report.job_id == job_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._row_to_dict(row) if row else None

    async def get_all(self) -> List[dict]:
        logger.info("Fetching all reports")
        stmt = select(Report).order_by(Report.ended_at.desc())
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        return [self._row_to_dict(row) for row in rows]

    async def get_ongoing_reports(self) -> List[dict]:
        logger.info("Fetching all ongoing reports")
        stmt = select(Report).where(Report.status == "ongoing")
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        return [self._row_to_dict(row) for row in rows]

    async def update_summary(
        self, job_id: str, summary: Optional[str], overall_score: int, status: str
    ) -> None:
        logger.info(f"Updating summary for report: {job_id} (status={status})")
        stmt = select(Report).where(Report.job_id == job_id)
        result = await self.session.execute(stmt)
        report = result.scalar_one_or_none()
        if report:
            report.summary = summary
            report.overall_score = overall_score
            report.status = status

    @staticmethod
    def _row_to_dict(row: Report) -> dict:
        """Converts a SQLAlchemy Report model instance to a plain dictionary."""
        return {
            "job_id": row.job_id,
            "room_id": row.room_id,
            "room": row.room,
            "started_at": row.started_at,
            "ended_at": row.ended_at,
            "duration_seconds": row.duration_seconds,
            "summary": row.summary,
            "overall_score": row.overall_score,
            "chat_history": row.chat_history,
            "status": row.status,
            "customer_name": row.customer_name,
            "agent_type": row.agent_type,
            "sales_rep": row.sales_rep,
            "scenario": row.scenario,
            "created_at": row.created_at,
        }

    @staticmethod
    def _compute_duration(started_at: str, ended_at: str) -> int:
        """Computes duration in seconds between two ISO timestamps."""
        try:
            fmt1 = "%Y-%m-%dT%H:%M:%S.%f"
            fmt2 = "%Y-%m-%dT%H:%M:%S"

            start_str = started_at.rstrip("Z").replace("+00:00", "")
            end_str = ended_at.rstrip("Z").replace("+00:00", "")

            try:
                start_dt = datetime.strptime(start_str, fmt1)
            except ValueError:
                start_dt = datetime.strptime(start_str, fmt2)

            try:
                end_dt = datetime.strptime(end_str, fmt1)
            except ValueError:
                end_dt = datetime.strptime(end_str, fmt2)

            return max(0, int((end_dt - start_dt).total_seconds()))
        except Exception:
            return 0
