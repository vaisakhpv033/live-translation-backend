import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from app.schemas.career_data import CareerDataCreate, CareerRecordDetail, CareerRecordListResponse
from app.services.career_data_service import ICareerRecordService
from app.api.dependencies import get_career_record_service

logger = logging.getLogger("translation-agent-backend.api.endpoints.career_data")
router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def receive_career_data(
    payload: CareerDataCreate,
    background_tasks: BackgroundTasks,
    career_service: ICareerRecordService = Depends(get_career_record_service),
):
    """
    Receives session reports from the career-agent on session end.
    Stores the initial payload and triggers background Gemini intake analysis.
    """
    try:
        result = await career_service.receive_career_data(payload)

        # Trigger background Gemini extraction of student details and conviction tiering
        chat_history_str = None
        if payload.chat_history:
            chat_history_str = json.dumps(payload.chat_history)

        background_tasks.add_task(
            career_service.extract_and_save_career_record,
            payload.job_id,
            chat_history_str,
            json.dumps(payload.summary) if payload.summary else None
        )

        return result
    except Exception as e:
        logger.error(f"Failed to process career data report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to receive career data: {str(e)}"
        )


@router.get("/", response_model=CareerRecordListResponse)
async def list_career_records(
    career_service: ICareerRecordService = Depends(get_career_record_service),
):
    """
    Lists all student career intake records with their structured information and conviction tiers.
    """
    try:
        return await career_service.list_career_records()
    except Exception as e:
        logger.error(f"Failed to list career records: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list career records: {str(e)}"
        )


@router.get("/{job_id}", response_model=CareerRecordDetail)
async def get_career_record(
    job_id: str,
    career_service: ICareerRecordService = Depends(get_career_record_service),
):
    """
    Retrieves full detail of a specific student career intake record by job ID.
    """
    record = await career_service.get_career_record(job_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Career record not found"
        )
    return record
