from typing import Optional
from fastapi import Depends
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.livekit import get_livekit_client, get_sts_livekit_client
from app.core.database import get_db_session
from app.services.livekit_service import IRoomService, LiveKitRoomService
from app.services.sts_room_service import ISTSRoomService, LiveKitSTSRoomService
from app.services.report_service import IReportService, ReportService
from app.services.career_data_service import ICareerRecordService, CareerRecordService
from app.services.evaluation_service import GeminiEvaluationService
from app.services.telephony_service import ITelephonyService, LiveKitTelephonyService
from app.repositories.report_repository import SQLAlchemyReportRepository
from app.repositories.career_data_repository import SQLAlchemyCareerRecordRepository


# ──────────────────────────────────────────────────────────────
#  Translation Agent Dependencies
# ──────────────────────────────────────────────────────────────

def get_livekit_api_client() -> api.LiveKitAPI:
    """
    FastAPI dependency that returns the active LiveKitAPI client.
    """
    return get_livekit_client()

def get_room_service(
    lk_client: api.LiveKitAPI = Depends(get_livekit_api_client)
) -> IRoomService:
    """
    FastAPI dependency that returns an instance of IRoomService.
    Ensures dependency inversion by returning the interface abstraction.
    """
    return LiveKitRoomService(lk_client)


# ──────────────────────────────────────────────────────────────
#  STS Agent Dependencies
# ──────────────────────────────────────────────────────────────

def get_sts_livekit_api_client() -> api.LiveKitAPI:
    """
    FastAPI dependency that returns the STS LiveKitAPI client.
    """
    return get_sts_livekit_client()

def get_sts_room_service(
    lk_client: api.LiveKitAPI = Depends(get_sts_livekit_api_client)
) -> ISTSRoomService:
    """
    FastAPI dependency that returns an ISTSRoomService backed by the STS LiveKit client.
    """
    return LiveKitSTSRoomService(lk_client)


# ──────────────────────────────────────────────────────────────
#  Telephony Dependencies (reuses the STS LiveKit client)
# ──────────────────────────────────────────────────────────────

def get_telephony_service(
    lk_client: api.LiveKitAPI = Depends(get_sts_livekit_api_client)
) -> ITelephonyService:
    """
    FastAPI dependency that returns an ITelephonyService backed by the STS LiveKit client.
    Reuses the same client that powers STS rooms — zero credential duplication.
    """
    return LiveKitTelephonyService(lk_client)


# ──────────────────────────────────────────────────────────────
#  Naaptol Order Confirmation Dependencies
# ──────────────────────────────────────────────────────────────

def get_order_confirmation_service(
    lk_client: api.LiveKitAPI = Depends(get_sts_livekit_api_client)
):
    """
    FastAPI dependency that returns an IOrderConfirmationService backed by the STS LiveKit client.
    """
    from app.services.order_confirmation_service import LiveKitOrderConfirmationService
    return LiveKitOrderConfirmationService(lk_client)



# ──────────────────────────────────────────────────────────────
#  Report Dependencies
# ──────────────────────────────────────────────────────────────

def get_report_service(
    db: AsyncSession = Depends(get_db_session)
) -> IReportService:
    """
    FastAPI dependency that returns an IReportService.
    Wires together the repository and evaluation service layers.
    """
    repository = SQLAlchemyReportRepository(db)
    evaluation_service = GeminiEvaluationService()
    return ReportService(repository, evaluation_service)


# ──────────────────────────────────────────────────────────────
#  Career Record Dependencies
# ──────────────────────────────────────────────────────────────

def get_career_record_service(
    db: AsyncSession = Depends(get_db_session)
) -> ICareerRecordService:
    """
    FastAPI dependency that returns an ICareerRecordService.
    Wires together the SQLAlchemy repository and Gemini evaluation service.
    """
    repository = SQLAlchemyCareerRecordRepository(db)
    evaluation_service = GeminiEvaluationService()
    return CareerRecordService(repository, evaluation_service)


# ──────────────────────────────────────────────────────────────
#  AutoCoach Dependencies (uses the STS LiveKit client)
# ──────────────────────────────────────────────────────────────

def get_autocoach_service(
    lk_client: api.LiveKitAPI = Depends(get_sts_livekit_api_client)
):
    """
    FastAPI dependency that returns an IAutoCoachService backed by the STS LiveKit client.
    """
    from app.services.autocoach_service import LiveKitAutoCoachService
    return LiveKitAutoCoachService(lk_client)


# ──────────────────────────────────────────────────────────────
#  Open Dental Patient Dependencies & API Key Protection
# ──────────────────────────────────────────────────────────────

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.core.config import get_settings

patient_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_patient_api_key(
    api_key: Optional[str] = Security(patient_api_key_header),
) -> str:
    """
    Guards patient search and retrieval endpoints.
    Requires incoming request to contain the valid secret in 'X-API-Key' header.
    Returns HTTP 403 Forbidden if invalid or missing.
    """
    settings = get_settings()
    expected_key = settings.PATIENT_API_KEY
    if not expected_key:
        return ""

    if not api_key or api_key.strip() != expected_key.strip():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or missing X-API-Key header. Please provide a valid patient API key in .env.",
        )
    return api_key


def get_patient_service():
    """
    FastAPI dependency that returns an OpenDentalPatientService.
    """
    from app.services.patient_service import OpenDentalPatientService
    return OpenDentalPatientService()


