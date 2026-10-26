import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from app.schemas.patient import (
    PatientSearchResponse,
    CacheStatsResponse,
    PatientAppointmentsResponse,
)
from app.services.patient_service import OpenDentalPatientService
from app.api.dependencies import get_patient_service, verify_patient_api_key

logger = logging.getLogger("translation-agent-backend.api.v1.endpoints.patients")

# Protect all patient endpoints with API Key verification dependency
router = APIRouter(dependencies=[Depends(verify_patient_api_key)])


@router.get(
    "/search",
    response_model=PatientSearchResponse,
    summary="Search & Filter Patients (LRU Cached with Python Sorting)",
)
async def search_patients(
    lname: Optional[str] = Query(default=None, min_length=2, description="Last Name (supports partial match, min 2 characters)"),
    fname: Optional[str] = Query(default=None, min_length=2, description="First Name (supports partial match, min 2 characters)"),
    phone: Optional[str] = Query(default=None, description="Wireless/Cell phone number"),
    birthdate: Optional[str] = Query(default=None, description="Birthdate in yyyy-MM-dd format"),
    patient_status: str = Query(default="Patient", alias="status", description="Patient status: 'Patient' (active), 'NonPatient', 'Inactive', 'Archived', etc."),
    gender: Optional[str] = Query(default=None, description="Gender: 'Male', 'Female', 'Unknown', 'Other'"),
    position: Optional[str] = Query(default=None, description="Marital status: 'Single', 'Married', 'Child', etc."),
    date_tstamp: Optional[str] = Query(default=None, description="Filter updated after timestamp: yyyy-MM-dd HH:mm:ss"),
    guarantor: Optional[int] = Query(default=None, description="PatNum of head of household / guarantor"),
    sort_by: Optional[str] = Query(default="lname", description="In-memory sort field: 'lname', 'fname', 'birthdate', 'patnum'"),
    order: str = Query(default="asc", description="Sort order: 'asc' or 'desc'"),
    limit: int = Query(default=50, ge=1, le=100, description="Max patients to return (max 100)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset (0, 50, 100...)"),
    service: OpenDentalPatientService = Depends(get_patient_service),
):
    """
    Searches patients from Open Dental `GET /patients/Simple` with fast LRU + TTL caching.
    
    Features:
    - **Ultra-fast cache hits (< 5ms)** via in-memory TTLCache.
    - **Case-insensitive cache key normalization** so 'Smith' and 'smith ' share the cache.
    - **In-memory Python sorting** by last name, first name, birthdate, or PatNum.
    - **Protected by X-API-Key header**.
    """
    try:
        return await service.search_patients(
            lname=lname,
            fname=fname,
            phone=phone,
            birthdate=birthdate,
            status=patient_status,
            gender=gender,
            position=position,
            date_tstamp=date_tstamp,
            guarantor=guarantor,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            order=order,
        )
    except Exception as e:
        logger.exception(f"Error querying patients: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query Open Dental patients: {str(e)}",
        )


@router.get(
    "/cache/stats",
    response_model=CacheStatsResponse,
    summary="Get Patient Search Cache Statistics",
)
async def get_cache_stats(
    service: OpenDentalPatientService = Depends(get_patient_service),
):
    """
    Returns current occupancy, maximum capacity, TTL, hits, and misses for the patient search cache.
    """
    return service.get_cache_stats()


@router.post(
    "/cache/clear",
    summary="Clear Patient In-Memory Caches",
)
async def clear_patient_cache(
    service: OpenDentalPatientService = Depends(get_patient_service),
):
    """
    Flushes the in-memory LRU search, detail, and appointment caches.
    """
    return service.clear_cache()


@router.get(
    "/{pat_num}/appointments",
    response_model=PatientAppointmentsResponse,
    summary="Get Patient Appointments with Status and Notes",
)
async def get_patient_appointments(
    pat_num: int,
    service: OpenDentalPatientService = Depends(get_patient_service),
):
    """
    Retrieves all appointment records for a specific PatNum from Open Dental API.
    
    Features:
    - Queries Open Dental `GET /appointments?PatNum={pat_num}`.
    - Full appointment details: scheduled date/time, procedure description, provider, and complete notes.
    - Explicit `is_completed` and `is_scheduled` status flags based on `AptStatus`.
    - Sorted chronologically descending (newest/upcoming first).
    - In-memory LRU + TTL caching (< 5ms on cache hit).
    - Protected by X-API-Key header.
    """
    try:
        return await service.get_patient_appointments(pat_num)
    except Exception as e:
        logger.exception(f"Error fetching appointments for patient {pat_num}: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch appointments from Open Dental: {str(e)}",
        )


@router.get(
    "/{pat_num}",
    summary="Get Single Patient Details",
)
async def get_patient_detail(
    pat_num: int,
    service: OpenDentalPatientService = Depends(get_patient_service),
):
    """
    Retrieves complete patient record details for a specific PatNum.
    """
    data = await service.get_patient_details(pat_num)
    if not data:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Patient with PatNum {pat_num} not found",
        )
    return data
