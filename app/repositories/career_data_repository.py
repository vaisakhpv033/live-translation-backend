import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime, UTC
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.career_data import CareerRecord

logger = logging.getLogger("translation-agent-backend.repositories.career_record")


class ICareerRecordRepository(ABC):
    """
    Interface for career record data access operations (SOLID Interface Segregation).
    """
    @abstractmethod
    async def save(self, record_data: dict) -> None:
        """Upserts a career intake record."""
        pass

    @abstractmethod
    async def get_by_job_id(self, job_id: str) -> Optional[dict]:
        """Retrieves a single career record by job_id."""
        pass

    @abstractmethod
    async def get_all(self) -> List[dict]:
        """Retrieves all career records ordered by created_at descending."""
        pass


class SQLAlchemyCareerRecordRepository(ICareerRecordRepository):
    """
    SQLAlchemy async implementation of ICareerRecordRepository.
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, record_data: dict) -> None:
        """
        Upserts a career record using PostgreSQL ON CONFLICT DO UPDATE.
        """
        logger.info(f"Saving career record: {record_data.get('job_id')}")

        now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        stmt = pg_insert(CareerRecord).values(
            job_id=record_data["job_id"],
            room_id=record_data.get("room_id"),
            student_name=record_data.get("student_name"),
            current_status=record_data.get("current_status"),
            next_study_program=record_data.get("next_study_program"),
            future_goals=record_data.get("future_goals"),
            plans_foreign_institutes=record_data.get("plans_foreign_institutes"),
            active_search_status=record_data.get("active_search_status"),
            conviction_tier=record_data.get("conviction_tier"),
            conviction_rationale=record_data.get("conviction_rationale"),
            chat_history=record_data.get("chat_history"),
            summary=record_data.get("summary"),
            created_at=now_iso,
        )

        # On conflict (job_id already exists), update all fields
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_id"],
            set_={
                "room_id": stmt.excluded.room_id,
                "student_name": stmt.excluded.student_name,
                "current_status": stmt.excluded.current_status,
                "next_study_program": stmt.excluded.next_study_program,
                "future_goals": stmt.excluded.future_goals,
                "plans_foreign_institutes": stmt.excluded.plans_foreign_institutes,
                "active_search_status": stmt.excluded.active_search_status,
                "conviction_tier": stmt.excluded.conviction_tier,
                "conviction_rationale": stmt.excluded.conviction_rationale,
                "chat_history": stmt.excluded.chat_history,
                "summary": stmt.excluded.summary,
                "created_at": stmt.excluded.created_at,
            }
        )

        await self.session.execute(stmt)
        await self.session.commit()

    async def get_by_job_id(self, job_id: str) -> Optional[dict]:
        logger.info(f"Fetching career record: {job_id}")
        stmt = select(CareerRecord).where(CareerRecord.job_id == job_id)
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._row_to_dict(row) if row else None

    async def get_all(self) -> List[dict]:
        logger.info("Fetching all career records")
        stmt = select(CareerRecord).order_by(CareerRecord.created_at.desc())
        result = await self.session.execute(stmt)
        rows = result.scalars().all()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: CareerRecord) -> dict:
        """Converts a SQLAlchemy CareerRecord model instance to a plain dictionary."""
        return {
            "job_id": row.job_id,
            "room_id": row.room_id,
            "student_name": row.student_name,
            "current_status": row.current_status,
            "next_study_program": row.next_study_program,
            "future_goals": row.future_goals,
            "plans_foreign_institutes": row.plans_foreign_institutes,
            "active_search_status": row.active_search_status,
            "conviction_tier": row.conviction_tier,
            "conviction_rationale": row.conviction_rationale,
            "chat_history": row.chat_history,
            "summary": row.summary,
            "created_at": row.created_at,
        }
