import hashlib
import logging
from typing import Optional, List, Dict, Any
import httpx
from cachetools import TTLCache

from app.core.config import get_settings
from app.schemas.appointment import (
    AppointmentItem,
    AppointmentDetailResponse,
    AppointmentListResponse,
)

logger = logging.getLogger("translation-agent-backend.services.appointment_service")
settings = get_settings()

# Module-level LRU + TTL caches
_appts_list_cache = TTLCache(maxsize=1000, ttl=300)      # 5 minutes TTL for date schedules
_appt_detail_cache = TTLCache(maxsize=1000, ttl=1800)    # 30 minutes TTL for single appointment detail

_cache_stats = {
    "hits": 0,
    "misses": 0
}


def generate_appts_cache_key(
    date: Optional[str] = None,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    status: Optional[str] = None,
    clinic_num: Optional[int] = None,
    pat_num: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> str:
    norm_date = (date or "").strip()
    norm_start = (date_start or "").strip()
    norm_end = (date_end or "").strip()
    norm_status = (status or "").strip().lower()
    norm_clinic = str(clinic_num or "")
    norm_pat = str(pat_num or "")
    raw = f"{norm_date}:{norm_start}:{norm_end}:{norm_status}:{norm_clinic}:{norm_pat}:{limit}:{offset}"
    hashed = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"appts_list:{hashed}"


class OpenDentalAppointmentService:
    """
    Service for querying appointments by date/range and retrieving single appointment details.
    Includes LRU caching, chronological sorting, and concurrent patient resolution.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 14.0,
    ):
        self.base_url = (base_url or settings.OPENDENTAL_BASE_URL).rstrip("/")
        self.headers = headers or settings.opendental_headers
        self.timeout = timeout

    async def get_appointments(
        self,
        date: Optional[str] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
        status: Optional[str] = None,
        clinic_num: Optional[int] = None,
        pat_num: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> AppointmentListResponse:
        """
        Retrieves appointments from Open Dental GET /appointments with filtering.
        """
        cache_key = generate_appts_cache_key(
            date=date,
            date_start=date_start,
            date_end=date_end,
            status=status,
            clinic_num=clinic_num,
            pat_num=pat_num,
            limit=limit,
            offset=offset,
        )

        if cache_key in _appts_list_cache:
            _cache_stats["hits"] += 1
            cached_data = _appts_list_cache[cache_key]
            logger.info(f"Cache HIT for appointments query: {cache_key} (count: {len(cached_data)})")
            return AppointmentListResponse(
                count=len(cached_data),
                date=date,
                date_start=date_start,
                date_end=date_end,
                cached=True,
                data=[AppointmentItem.model_validate(a) for a in cached_data],
            )

        _cache_stats["misses"] += 1
        logger.info(f"Cache MISS for appointments query. Fetching from Open Dental...")

        params: Dict[str, Any] = {
            "Offset": offset,
            "Limit": min(200, max(1, limit)),
        }
        if date and date.strip():
            params["date"] = date.strip()
        if date_start and date_start.strip():
            params["dateStart"] = date_start.strip()
        if date_end and date_end.strip():
            params["dateEnd"] = date_end.strip()
        if status and status.strip():
            params["AptStatus"] = status.strip()
        if clinic_num is not None:
            params["ClinicNum"] = clinic_num
        if pat_num is not None:
            params["PatNum"] = pat_num

        url = f"{self.base_url}/appointments"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, headers=self.headers, params=params)
                if res.status_code == 200:
                    raw_data = res.json()
                    if not isinstance(raw_data, list):
                        raw_data = []

                    # Sort chronologically ascending (morning to evening)
                    def appt_time_key(item: Dict[str, Any]) -> str:
                        return str(item.get("AptDateTime") or "")

                    sorted_appts = sorted(raw_data, key=appt_time_key)
                    _appts_list_cache[cache_key] = sorted_appts

                    return AppointmentListResponse(
                        count=len(sorted_appts),
                        date=date,
                        date_start=date_start,
                        date_end=date_end,
                        cached=False,
                        data=[AppointmentItem.model_validate(a) for a in sorted_appts],
                    )
                elif res.status_code == 404:
                    return AppointmentListResponse(
                        count=0,
                        date=date,
                        date_start=date_start,
                        date_end=date_end,
                        cached=False,
                        data=[],
                    )
                else:
                    logger.error(f"Open Dental GET /appointments error {res.status_code}: {res.text[:300]}")
                    return AppointmentListResponse(
                        count=0,
                        date=date,
                        date_start=date_start,
                        date_end=date_end,
                        cached=False,
                        data=[],
                    )
            except Exception as e:
                logger.exception(f"HTTP error querying appointments: {e}")
                raise

    async def get_appointment_by_id(
        self,
        apt_num: int,
        include_patient: bool = True,
    ) -> Optional[AppointmentDetailResponse]:
        """
        Retrieves full details for a single appointment from GET /appointments/{apt_num}.
        If include_patient is True, embeds full patient demographics from GET /patients/{pat_num}.
        """
        cache_key = f"appt_detail:{apt_num}:{include_patient}"
        if cache_key in _appt_detail_cache:
            _cache_stats["hits"] += 1
            cached_item = _appt_detail_cache[cache_key]
            logger.info(f"Cache HIT for appointment detail #{apt_num}")
            return AppointmentDetailResponse.model_validate({**cached_item, "cached": True})

        _cache_stats["misses"] += 1
        logger.info(f"Cache MISS for appointment detail #{apt_num}. Fetching from Open Dental...")

        url = f"{self.base_url}/appointments/{apt_num}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, headers=self.headers)
                if res.status_code == 200:
                    appt_data = res.json()
                    pat_num = appt_data.get("PatNum")

                    # Concurrently/subsequently fetch patient details if requested
                    patient_data = None
                    if include_patient and pat_num:
                        pat_url = f"{self.base_url}/patients/{pat_num}"
                        try:
                            pat_res = await client.get(pat_url, headers=self.headers)
                            if pat_res.status_code == 200:
                                patient_data = pat_res.json()
                        except Exception as pe:
                            logger.warning(f"Could not load patient #{pat_num} for appt #{apt_num}: {pe}")

                    combined = {**appt_data, "patient": patient_data}
                    _appt_detail_cache[cache_key] = combined

                    return AppointmentDetailResponse.model_validate({**combined, "cached": False})
                elif res.status_code == 404:
                    return None
                else:
                    logger.error(f"Error fetching appointment #{apt_num}: status {res.status_code}")
                    return None
            except Exception as e:
                logger.exception(f"HTTP error fetching appointment #{apt_num}: {e}")
                raise

    def clear_cache(self) -> Dict[str, Any]:
        """Flushes in-memory appointment caches."""
        cleared_list = len(_appts_list_cache)
        cleared_detail = len(_appt_detail_cache)
        _appts_list_cache.clear()
        _appt_detail_cache.clear()
        _cache_stats["hits"] = 0
        _cache_stats["misses"] = 0
        return {
            "status": "success",
            "message": "Appointment caches flushed successfully",
            "cleared_list_entries": cleared_list,
            "cleared_detail_entries": cleared_detail,
        }
