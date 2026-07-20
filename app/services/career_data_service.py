import json
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from app.schemas.career_data import CareerDataCreate, CareerRecordDetail, CareerRecordListResponse
from app.repositories.career_data_repository import ICareerRecordRepository
from app.services.evaluation_service import IEvaluationService

logger = logging.getLogger("translation-agent-backend.services.career_data_service")


class ICareerRecordService(ABC):
    """
    Interface for career record business operations (SOLID Interface Segregation).
    """
    @abstractmethod
    async def receive_career_data(self, payload: CareerDataCreate) -> dict:
        """Receives and stores an initial career report, returns acknowledgement."""
        pass

    @abstractmethod
    async def list_career_records(self) -> CareerRecordListResponse:
        """Lists all career intake records."""
        pass

    @abstractmethod
    async def get_career_record(self, job_id: str) -> Optional[CareerRecordDetail]:
        """Returns full career record detail by job_id."""
        pass

    @abstractmethod
    async def extract_and_save_career_record(
        self, job_id: str, chat_history_str: Optional[str], summary: Optional[str]
    ) -> None:
        """Asynchronously calls Gemini to extract structured career details and save them."""
        pass


class CareerRecordService(ICareerRecordService):
    """
    Career record business logic implementation (Dependency Inversion).
    Coordination layer between database repository and Gemini extraction services.
    """
    def __init__(
        self,
        repository: ICareerRecordRepository,
        evaluation_service: IEvaluationService,
    ):
        self.repository = repository
        self.evaluation_service = evaluation_service

    async def receive_career_data(self, payload: CareerDataCreate) -> dict:
        logger.info(f"Registering incoming career data report: {payload.job_id}")

        chat_history_str = None
        if payload.chat_history:
            chat_history_str = json.dumps(payload.chat_history)

        summary_str = None
        if payload.summary:
            summary_str = (
                payload.summary if isinstance(payload.summary, str) else json.dumps(payload.summary)
            )

        # Save initial basic payload (student name resolved from default if any)
        initial_record = {
            "job_id": payload.job_id,
            "room_id": payload.room_id,
            "student_name": payload.customer_name or "Student",
            "chat_history": chat_history_str,
            "summary": summary_str,
        }
        await self.repository.save(initial_record)

        return {
            "status": "success",
            "message": "Career record registered successfully. Detail extraction pending.",
            "job_id": payload.job_id
        }

    async def list_career_records(self) -> CareerRecordListResponse:
        records_raw = await self.repository.get_all()
        records_detail = []
        for r in records_raw:
            records_detail.append(CareerRecordDetail(**r))
        return CareerRecordListResponse(records=records_detail)

    async def get_career_record(self, job_id: str) -> Optional[CareerRecordDetail]:
        record_raw = await self.repository.get_by_job_id(job_id)
        if not record_raw:
            return None
        return CareerRecordDetail(**record_raw)

    async def extract_and_save_career_record(
        self, job_id: str, chat_history_str: Optional[str], summary: Optional[str]
    ) -> None:
        logger.info(f"Running background Gemini detail extraction for job: {job_id}")
        
        # Load existing record so we can preserve fields
        existing = await self.repository.get_by_job_id(job_id)
        if not existing:
            logger.error(f"Cannot find career record for extraction: {job_id}")
            return

        try:
            extracted = await self.evaluation_service.extract_career_details(chat_history_str)
            if not extracted:
                logger.error(f"Failed to extract career details from Gemini for job {job_id}")
                return

            logger.info(f"Gemini successfully extracted career details for job {job_id}")

            # Merge Gemini extracted fields into existing database dict
            existing["student_name"] = extracted.get("student_name", existing.get("student_name"))
            existing["current_status"] = extracted.get("current_status")
            existing["next_study_program"] = extracted.get("next_study_program")
            existing["future_goals"] = extracted.get("future_goals")
            existing["plans_foreign_institutes"] = extracted.get("plans_foreign_institutes")
            existing["active_search_status"] = extracted.get("active_search_status")
            existing["conviction_tier"] = extracted.get("conviction_tier")
            existing["conviction_rationale"] = extracted.get("conviction_rationale")

            await self.repository.save(existing)
        except Exception as e:
            logger.error(f"Exception during background career details extraction for job {job_id}: {e}")
