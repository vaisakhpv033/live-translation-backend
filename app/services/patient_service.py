import hashlib
import logging
from typing import Optional, List, Dict, Any, Tuple
import httpx
from cachetools import TTLCache

from app.core.config import get_settings
from app.schemas.patient import (
    PatientSimple,
    PatientSearchResponse,
    CacheStatsResponse,
    AppointmentItem,
    PatientAppointmentsResponse,
)

logger = logging.getLogger("translation-agent-backend.services.patient_service")
settings = get_settings()

# Module-level LRU + TTL caches (singleton per process)
_search_cache = TTLCache(
    maxsize=settings.PATIENT_CACHE_MAXSIZE,
    ttl=settings.PATIENT_CACHE_TTL
)
_detail_cache = TTLCache(
    maxsize=1000,
    ttl=settings.PATIENT_CACHE_TTL
)
_appointment_cache = TTLCache(
    maxsize=1000,
    ttl=settings.PATIENT_CACHE_TTL
)

_cache_stats = {
    "hits": 0,
    "misses": 0
}


def generate_search_cache_key(
    lname: Optional[str] = None,
    fname: Optional[str] = None,
    phone: Optional[str] = None,
    birthdate: Optional[str] = None,
    status: Optional[str] = None,
    gender: Optional[str] = None,
    position: Optional[str] = None,
    date_tstamp: Optional[str] = None,
    guarantor: Optional[int] = None,
    offset: int = 0,
    limit: int = 50,
    sort_by: Optional[str] = None,
    order: str = "asc",
) -> str:
    """
    Creates a normalized unique MD5 hash for the search parameters.
    Normalizes casing and whitespace to ensure maximum cache hit ratio.
    """
    norm_lname = (lname or "").strip().lower()
    norm_fname = (fname or "").strip().lower()
    norm_phone = (phone or "").strip().replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    norm_dob = (birthdate or "").strip()
    norm_status = (status or "patient").strip().lower()
    norm_gender = (gender or "").strip().lower()
    norm_position = (position or "").strip().lower()
    norm_tstamp = (date_tstamp or "").strip()
    norm_guar = str(guarantor or "")
    norm_sort = (sort_by or "patnum").strip().lower()
    norm_order = (order or "asc").strip().lower()

    raw_signature = (
        f"{norm_lname}:{norm_fname}:{norm_phone}:{norm_dob}:{norm_status}:"
        f"{norm_gender}:{norm_position}:{norm_tstamp}:{norm_guar}:{offset}:{limit}:"
        f"{norm_sort}:{norm_order}"
    )
    hashed = hashlib.md5(raw_signature.encode("utf-8")).hexdigest()
    return f"patients_search:{hashed}"


def sort_patients(patients: List[Dict[str, Any]], sort_by: Optional[str], order: str = "asc") -> List[Dict[str, Any]]:
    """
    Applies pure Python sorting to the list of patients returned by Open Dental.
    Open Dental natively only sorts by PatNum ASC.
    """
    if not sort_by or not patients:
        return patients

    sort_key = sort_by.strip().lower()
    reverse = (order.strip().lower() == "desc")

    if sort_key in ("lname", "lastname", "last_name"):
        return sorted(
            patients,
            key=lambda p: (str(p.get("LName") or "").lower(), str(p.get("FName") or "").lower()),
            reverse=reverse
        )
    elif sort_key in ("fname", "firstname", "first_name"):
        return sorted(
            patients,
            key=lambda p: (str(p.get("FName") or "").lower(), str(p.get("LName") or "").lower()),
            reverse=reverse
        )
    elif sort_key in ("birthdate", "dob"):
        return sorted(
            patients,
            key=lambda p: str(p.get("Birthdate") or ""),
            reverse=reverse
        )
    elif sort_key in ("patnum", "id"):
        return sorted(
            patients,
            key=lambda p: int(p.get("PatNum") or 0),
            reverse=reverse
        )
    return patients


class OpenDentalPatientService:
    """
    High-performance patient search and appointment service with LRU + TTL Cache-Aside and Python sorting.
    """
    def __init__(
        self,
        base_url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 12.0,
    ):
        self.base_url = (base_url or settings.OPENDENTAL_BASE_URL).rstrip("/")
        self.headers = headers or settings.opendental_headers
        self.timeout = timeout

    async def search_patients(
        self,
        lname: Optional[str] = None,
        fname: Optional[str] = None,
        phone: Optional[str] = None,
        birthdate: Optional[str] = None,
        status: str = "Patient",
        gender: Optional[str] = None,
        position: Optional[str] = None,
        date_tstamp: Optional[str] = None,
        guarantor: Optional[int] = None,
        offset: int = 0,
        limit: int = 50,
        sort_by: Optional[str] = "lname",
        order: str = "asc",
    ) -> PatientSearchResponse:
        """
        Queries Open Dental GET /patients/Simple with LRU cache-aside optimization.
        """
        # 1. Compute normalized cache key
        cache_key = generate_search_cache_key(
            lname=lname,
            fname=fname,
            phone=phone,
            birthdate=birthdate,
            status=status,
            gender=gender,
            position=position,
            date_tstamp=date_tstamp,
            guarantor=guarantor,
            offset=offset,
            limit=limit,
            sort_by=sort_by,
            order=order,
        )

        # 2. Check LRU Cache
        if cache_key in _search_cache:
            _cache_stats["hits"] += 1
            cached_data = _search_cache[cache_key]
            logger.info(f"LRU Cache HIT for search: {cache_key} (patients: {len(cached_data)})")
            return PatientSearchResponse(
                cached=True,
                count=len(cached_data),
                limit=limit,
                offset=offset,
                data=[PatientSimple.model_validate(p) for p in cached_data],
            )

        _cache_stats["misses"] += 1
        logger.info(f"LRU Cache MISS for search: {cache_key}. Fetching from Open Dental...")

        # 3. Construct Open Dental Query Parameters
        params: Dict[str, Any] = {
            "Offset": offset,
            "Limit": min(100, max(1, limit)),
        }
        if status:
            params["PatStatus"] = status.strip()
        if lname and lname.strip():
            params["LName"] = lname.strip()
        if fname and fname.strip():
            params["FName"] = fname.strip()
        if phone and phone.strip():
            params["WirelessPhone"] = phone.strip()
        if birthdate and birthdate.strip():
            params["Birthdate"] = birthdate.strip()
        if gender and gender.strip():
            params["Gender"] = gender.strip()
        if position and position.strip():
            params["Position"] = position.strip()
        if date_tstamp and date_tstamp.strip():
            params["DateTStamp"] = date_tstamp.strip()
        if guarantor is not None:
            params["Guarantor"] = guarantor

        url = f"{self.base_url}/patients/Simple"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, headers=self.headers, params=params)
                if res.status_code == 200:
                    raw_patients = res.json()
                    if not isinstance(raw_patients, list):
                        raw_patients = []

                    # 4. In-Memory Sorting
                    sorted_patients = sort_patients(raw_patients, sort_by=sort_by, order=order)

                    # 5. Store in LRU Cache
                    _search_cache[cache_key] = sorted_patients

                    return PatientSearchResponse(
                        cached=False,
                        count=len(sorted_patients),
                        limit=limit,
                        offset=offset,
                        data=[PatientSimple.model_validate(p) for p in sorted_patients],
                    )
                else:
                    logger.error(
                        f"Open Dental /patients/Simple error {res.status_code}: {res.text[:300]}"
                    )
                    return PatientSearchResponse(
                        cached=False,
                        count=0,
                        limit=limit,
                        offset=offset,
                        data=[],
                    )
            except Exception as e:
                logger.exception(f"HTTP error fetching patients from Open Dental: {e}")
                raise

    async def get_patient_details(self, pat_num: int) -> Optional[Dict[str, Any]]:
        """
        Retrieves full patient details for a single patient using GET /patients/{pat_num}.
        Uses detail LRU cache.
        """
        cache_key = f"patient_detail:{pat_num}"
        if cache_key in _detail_cache:
            return _detail_cache[cache_key]

        url = f"{self.base_url}/patients/{pat_num}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, headers=self.headers)
                if res.status_code == 200:
                    data = res.json()
                    _detail_cache[cache_key] = data
                    return data
                elif res.status_code == 404:
                    return None
                else:
                    logger.warning(f"Error fetching patient {pat_num}: {res.status_code}")
                    return None
            except Exception as e:
                logger.error(f"Failed to fetch patient detail for {pat_num}: {e}")
                return None

    async def get_patient_appointments(self, pat_num: int) -> PatientAppointmentsResponse:
        """
        Retrieves all appointments for a patient using Open Dental GET /appointments?PatNum={pat_num}.
        Uses appointment LRU + TTL cache and sorts newest/upcoming appointments first.
        """
        cache_key = f"patient_appointments:{pat_num}"
        if cache_key in _appointment_cache:
            _cache_stats["hits"] += 1
            cached_appts = _appointment_cache[cache_key]
            logger.info(f"LRU Cache HIT for appointments of patient #{pat_num} (count: {len(cached_appts)})")
            return PatientAppointmentsResponse(
                pat_num=pat_num,
                count=len(cached_appts),
                cached=True,
                appointments=[AppointmentItem.model_validate(a) for a in cached_appts],
            )

        _cache_stats["misses"] += 1
        logger.info(f"LRU Cache MISS for appointments of patient #{pat_num}. Fetching from Open Dental...")

        url = f"{self.base_url}/appointments"
        params = {"PatNum": pat_num}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                res = await client.get(url, headers=self.headers, params=params)
                if res.status_code == 200:
                    raw_data = res.json()
                    if not isinstance(raw_data, list):
                        raw_data = []

                    # Sort appointments descending by AptDateTime so newest/upcoming come first
                    def parse_appt_date(item: Dict[str, Any]) -> str:
                        return str(item.get("AptDateTime") or "")

                    sorted_appts = sorted(raw_data, key=parse_appt_date, reverse=True)

                    # Store in LRU cache
                    _appointment_cache[cache_key] = sorted_appts

                    return PatientAppointmentsResponse(
                        pat_num=pat_num,
                        count=len(sorted_appts),
                        cached=False,
                        appointments=[AppointmentItem.model_validate(a) for a in sorted_appts],
                    )
                elif res.status_code == 404:
                    logger.info(f"No appointments found (404) for patient #{pat_num}")
                    return PatientAppointmentsResponse(
                        pat_num=pat_num,
                        count=0,
                        cached=False,
                        appointments=[],
                    )
                else:
                    logger.error(
                        f"Open Dental GET /appointments error {res.status_code} for PatNum {pat_num}: {res.text[:300]}"
                    )
                    return PatientAppointmentsResponse(
                        pat_num=pat_num,
                        count=0,
                        cached=False,
                        appointments=[],
                    )
            except Exception as e:
                logger.exception(f"HTTP error fetching appointments for patient #{pat_num}: {e}")
                raise

    def clear_cache(self) -> Dict[str, Any]:
        """Flushes the in-memory search, detail, and appointment caches."""
        cleared_search = len(_search_cache)
        cleared_detail = len(_detail_cache)
        cleared_appts = len(_appointment_cache)
        _search_cache.clear()
        _detail_cache.clear()
        _appointment_cache.clear()
        _cache_stats["hits"] = 0
        _cache_stats["misses"] = 0
        return {
            "status": "success",
            "message": "Patient caches flushed successfully",
            "cleared_search_entries": cleared_search,
            "cleared_detail_entries": cleared_detail,
            "cleared_appointment_entries": cleared_appts,
        }

    def get_cache_stats(self) -> CacheStatsResponse:
        """Returns cache occupancy and hit/miss statistics."""
        return CacheStatsResponse(
            currsize=len(_search_cache),
            maxsize=settings.PATIENT_CACHE_MAXSIZE,
            ttl=settings.PATIENT_CACHE_TTL,
            hits=_cache_stats["hits"],
            misses=_cache_stats["misses"],
        )
