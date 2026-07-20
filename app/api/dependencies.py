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

