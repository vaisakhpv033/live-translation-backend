import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status as http_status

from app.schemas.appointment import (
    AppointmentListResponse,
    AppointmentDetailResponse,
)
from app.services.appointment_service import OpenDentalAppointmentService
from app.api.dependencies import get_appointment_service, verify_patient_api_key

logger = logging.getLogger("translation-agent-backend.api.v1.endpoints.appointments")

# Protected by X-API-Key dependency
router = APIRouter(dependencies=[Depends(verify_patient_api_key)])


@router.get(
    "",
    response_model=AppointmentListResponse,
    summary="List Appointments by Date or Date Range",
)
async def list_appointments(
    date: Optional[str] = Query(default=None, description="Specific appointment date in yyyy-MM-dd format"),
    date_start: Optional[str] = Query(default=None, alias="dateStart", description="Range start date in yyyy-MM-dd format"),
    date_end: Optional[str] = Query(default=None, alias="dateEnd", description="Range end date in yyyy-MM-dd format"),
    status: Optional[str] = Query(default=None, description="Filter by status: 'Scheduled', 'Complete', 'Broken', 'Planned', etc."),
    clinic_num: Optional[int] = Query(default=None, alias="ClinicNum", description="Filter by clinic ID"),
    pat_num: Optional[int] = Query(default=None, alias="PatNum", description="Filter by patient ID"),
    limit: int = Query(default=100, ge=1, le=200, description="Max appointments to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    service: OpenDentalAppointmentService = Depends(get_appointment_service),
):
    """
    Retrieves appointments from Open Dental API filtered by date, date range, status, or clinic.
    
    Features:
    - Default view queryable by today's date (`?date=2026-10-26`).
    - Date range search supported (`?dateStart=2026-10-26&dateEnd=2026-10-30`).
    - Sorted chronologically ascending (earliest to latest in the day).
    - LRU TTL cached for rapid switching between schedule dates (< 5ms).
    - Protected by X-API-Key header.
    """
    try:
        return await service.get_appointments(
            date=date,
            date_start=date_start,
            date_end=date_end,
            status=status,
            clinic_num=clinic_num,
            pat_num=pat_num,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.exception(f"Error fetching appointments: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch appointments: {str(e)}",
        )


@router.get(
    "/cache/clear",
    summary="Clear Appointment Cache",
)
async def clear_appointment_cache(
    service: OpenDentalAppointmentService = Depends(get_appointment_service),
):
    """Flushes in-memory appointment search and detail caches."""
    return service.clear_cache()


@router.get(
    "/{apt_num}",
    response_model=AppointmentDetailResponse,
    summary="Get Single Appointment Details with Patient Profile",
)
async def get_appointment_detail(
    apt_num: int = Path(..., ge=1, description="Appointment ID (AptNum)"),
    include_patient: bool = Query(default=True, description="Whether to include full patient record"),
    service: OpenDentalAppointmentService = Depends(get_appointment_service),
):
    """
    Retrieves full details for a single appointment by AptNum.
    
    Features:
    - Fetches full appointment record (`GET /appointments/{aptNum}`).
    - Embeds complete patient profile (`GET /patients/{patNum}`) including balances, contact info, and medical notes.
    - LRU cached for quick retrieval.
    - Protected by X-API-Key header.
    """
    data = await service.get_appointment_by_id(apt_num=apt_num, include_patient=include_patient)
    if not data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Appointment with AptNum {apt_num} not found",
        )
    return data
