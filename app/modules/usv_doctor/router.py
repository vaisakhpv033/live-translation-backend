"""Dedicated FastAPI router for USV Doctor Detailing sessions, webhooks, and QA reports."""

from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)
from livekit import api
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.livekit import get_sts_livekit_client
from app.modules.usv_doctor.repository import UsvDoctorReportRepository
from app.modules.usv_doctor.schemas import (
    UsvDoctorReportDetail,
    UsvDoctorReportListResponse,
    UsvDoctorSessionCreate,
    UsvDoctorSessionResponse,
    UsvDoctorTokenRequest,
    UsvDoctorWebhookPayload,
)
from app.modules.usv_doctor.service import UsvDoctorService
from app.schemas.room import RoomResponse
from app.schemas.token import TokenResponse
from app.services.background_evaluation import run_usv_doctor_background_evaluation

router = APIRouter()
settings = get_settings()


def _get_livekit_usv_service(
    lk_client: api.LiveKitAPI = Depends(get_sts_livekit_client),
) -> UsvDoctorService:
    return UsvDoctorService(lk_client=lk_client)


def _get_report_usv_service(
    db: AsyncSession = Depends(get_db_session),
) -> UsvDoctorService:
    return UsvDoctorService(repository=UsvDoctorReportRepository(db))


def _verify_webhook_secret(
    x_api_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    expected = (getattr(settings, "AUTOCOACH_REPORT_WEBHOOK_SECRET", "") or "").strip()
    if not expected:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    if x_api_key == expected or bearer == expected:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid webhook authentication credentials.",
    )


@router.post(
    "/start-session",
    response_model=UsvDoctorSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start USV Doctor Detailing Session with Agent Handshake",
)
async def start_session(
    payload: UsvDoctorSessionCreate,
    service: UsvDoctorService = Depends(_get_livekit_usv_service),
):
    try:
        return await service.create_and_dispatch_session(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start USV Doctor session: {exc}",
        )


@router.get("/rooms", response_model=List[RoomResponse], summary="List Active USV Doctor Rooms")
async def list_rooms(service: UsvDoctorService = Depends(_get_livekit_usv_service)):
    return await service.list_sessions()


@router.get("/rooms/{room_name}", response_model=RoomResponse, summary="Get USV Doctor Room Details")
async def get_room(room_name: str, service: UsvDoctorService = Depends(_get_livekit_usv_service)):
    room = await service.get_session(room_name)
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Room '{room_name}' not found")
    return room


@router.delete("/rooms/{room_name}", status_code=status.HTTP_200_OK, summary="Close USV Doctor Room")
async def delete_room(room_name: str, service: UsvDoctorService = Depends(_get_livekit_usv_service)):
    success = await service.delete_session(room_name)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close room '{room_name}'",
        )
    return {"status": "success", "message": f"Room '{room_name}' closed successfully"}


@router.post("/rooms/{room_name}/token", response_model=TokenResponse, summary="Generate USV Doctor Room Token")
async def generate_token(
    room_name: str,
    token_req: UsvDoctorTokenRequest,
    service: UsvDoctorService = Depends(_get_livekit_usv_service),
):
    return service.generate_token(room_name, token_req)


@router.post(
    "/reports",
    status_code=status.HTTP_201_CREATED,
    summary="Receive Autocoach-agent Post-Call Telemetry Webhook",
)
async def receive_report(
    payload: UsvDoctorWebhookPayload,
    background_tasks: BackgroundTasks,
    service: UsvDoctorService = Depends(_get_report_usv_service),
    _: None = Depends(_verify_webhook_secret),
):
    result = await service.receive_report(payload)
    background_tasks.add_task(run_usv_doctor_background_evaluation, payload.job_id)
    return result


@router.get("/reports", response_model=UsvDoctorReportListResponse, summary="List USV Doctor Reports")
async def list_reports(service: UsvDoctorService = Depends(_get_report_usv_service)):
    return await service.list_reports()


@router.get("/reports/{job_id}", response_model=UsvDoctorReportDetail, summary="Get USV Doctor Report Detail")
async def get_report(job_id: str, service: UsvDoctorService = Depends(_get_report_usv_service)):
    report = await service.get_report(job_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USV Doctor report not found")
    return report


@router.get("/reports/{job_id}/status", summary="Get USV Doctor Evaluation Status")
async def get_report_status(
    job_id: str,
    response: Response,
    service: UsvDoctorService = Depends(_get_report_usv_service),
):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    result = await service.get_report_status(job_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USV Doctor report not found")
    return result


@router.post("/reports/{job_id}/retry", summary="Retry USV Doctor QA Evaluation")
async def retry_report(
    job_id: str,
    background_tasks: BackgroundTasks,
    service: UsvDoctorService = Depends(_get_report_usv_service),
):
    row = await service.retry_evaluation(job_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="USV Doctor report not found")
    background_tasks.add_task(run_usv_doctor_background_evaluation, job_id)
    return {"status": "success", "message": f"Retry evaluation started for USV Doctor job {job_id}."}
