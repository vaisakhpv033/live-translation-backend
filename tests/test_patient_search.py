import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.services.patient_service import (
    generate_search_cache_key,
    sort_patients,
    OpenDentalPatientService,
)
from app.schemas.patient import PatientSearchResponse, PatientSimple
from app.api.dependencies import get_patient_service


TEST_API_KEY = "autocoach-dental-secret-key-2026"


# ──────────────────────────────────────────────────────────────
#  1. Unit Tests: Cache Key Normalization & In-Memory Sorting
# ──────────────────────────────────────────────────────────────

def test_generate_search_cache_key_normalization():
    # Case and whitespace variations must yield identical MD5 cache keys
    key1 = generate_search_cache_key(lname="Smith", fname="Daniel", status="Patient")
    key2 = generate_search_cache_key(lname="smith ", fname="  daniel", status="patient")
    assert key1 == key2

    # Different search parameters must yield different keys
    key3 = generate_search_cache_key(lname="Miller", fname="Daniel", status="Patient")
    assert key1 != key3

    # Phone normalization with dashes/spaces
    phone_key1 = generate_search_cache_key(phone="(972) 555-0199")
    phone_key2 = generate_search_cache_key(phone="9725550199")
    phone_key3 = generate_search_cache_key(phone="972-555-0199")
    assert phone_key1 == phone_key2 == phone_key3


def test_sort_patients_in_memory():
    sample_patients = [
        {"PatNum": 3, "LName": "Zimmerman", "FName": "Alice", "Birthdate": "1995-01-01"},
        {"PatNum": 1, "LName": "Adams", "FName": "Charlie", "Birthdate": "1980-05-12"},
        {"PatNum": 2, "LName": "Miller", "FName": "Bob", "Birthdate": "2000-11-20"},
    ]

    # Sort by LName ASC
    sorted_lname_asc = sort_patients(sample_patients, sort_by="lname", order="asc")
    assert [p["LName"] for p in sorted_lname_asc] == ["Adams", "Miller", "Zimmerman"]

    # Sort by LName DESC
    sorted_lname_desc = sort_patients(sample_patients, sort_by="lname", order="desc")
    assert [p["LName"] for p in sorted_lname_desc] == ["Zimmerman", "Miller", "Adams"]

    # Sort by FName ASC
    sorted_fname_asc = sort_patients(sample_patients, sort_by="fname", order="asc")
    assert [p["FName"] for p in sorted_fname_asc] == ["Alice", "Bob", "Charlie"]

    # Sort by Birthdate ASC
    sorted_dob_asc = sort_patients(sample_patients, sort_by="birthdate", order="asc")
    assert [p["PatNum"] for p in sorted_dob_asc] == [1, 3, 2]

    # Sort by PatNum DESC
    sorted_patnum_desc = sort_patients(sample_patients, sort_by="patnum", order="desc")
    assert [p["PatNum"] for p in sorted_patnum_desc] == [3, 2, 1]


# ──────────────────────────────────────────────────────────────
#  2. Service Tests: LRU Cache-Aside (Hit / Miss / Flush)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_cache_aside_flow():
    service = OpenDentalPatientService(base_url="https://mock.opendental.com/api/v1")
    service.clear_cache()

    mock_raw_data = [
        {
            "PatNum": 101,
            "LName": "Smith",
            "FName": "John",
            "PatStatus": "Patient",
            "WirelessPhone": "9725550199",
            "Birthdate": "1985-04-12",
        }
    ]

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_raw_data
        mock_get.return_value = mock_response

        # 1. First Call: Cache MISS (must call Open Dental)
        res1 = await service.search_patients(lname="Smith")
        assert res1.cached is False
        assert res1.count == 1
        assert res1.data[0].LName == "Smith"
        assert mock_get.call_count == 1

        # 2. Second Call with same / normalized query: Cache HIT (must NOT call Open Dental)
        res2 = await service.search_patients(lname=" smith ")
        assert res2.cached is True
        assert res2.count == 1
        assert res2.data[0].LName == "Smith"
        assert mock_get.call_count == 1  # Still 1! Served from memory

        # 3. Check stats
        stats = service.get_cache_stats()
        assert stats.hits >= 1
        assert stats.misses >= 1

        # 4. Clear cache and query again: Cache MISS
        service.clear_cache()
        res3 = await service.search_patients(lname="Smith")
        assert res3.cached is False
        assert mock_get.call_count == 2


# ──────────────────────────────────────────────────────────────
#  3. API Endpoint Tests: X-API-Key Security & Query Filtering
# ──────────────────────────────────────────────────────────────

def test_api_security_missing_or_invalid_api_key():
    client = TestClient(app)

    # Missing API Key -> 403 Forbidden
    res_no_key = client.get("/api/v1/patients/search?lname=Smith")
    assert res_no_key.status_code == 403
    assert "Invalid or missing X-API-Key" in res_no_key.json()["detail"]

    # Invalid API Key -> 403 Forbidden
    res_bad_key = client.get(
        "/api/v1/patients/search?lname=Smith",
        headers={"X-API-Key": "wrong-key"}
    )
    assert res_bad_key.status_code == 403


def test_api_search_patients_with_valid_key():
    mock_service = MagicMock(spec=OpenDentalPatientService)
    mock_service.search_patients = AsyncMock(
        return_value=PatientSearchResponse(
            cached=False,
            count=1,
            limit=50,
            offset=0,
            data=[
                PatientSimple(
                    PatNum=101,
                    LName="Smith",
                    FName="Daniel",
                    PatStatus="Patient",
                    WirelessPhone="(972) 555-0199",
                    Birthdate="1988-06-15",
                )
            ]
        )
    )

    app.dependency_overrides[get_patient_service] = lambda: mock_service
    client = TestClient(app)

    try:
        response = client.get(
            "/api/v1/patients/search?lname=Smith&fname=Dan&status=Patient&sort_by=lname&order=asc",
            headers={"X-API-Key": TEST_API_KEY}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is False
        assert data["count"] == 1
        assert data["data"][0]["PatNum"] == 101
        assert data["data"][0]["LName"] == "Smith"
        assert data["data"][0]["FName"] == "Daniel"
    finally:
        app.dependency_overrides.clear()


def test_api_search_min_length_validation():
    client = TestClient(app)

    # LName < 2 chars -> 422 Unprocessable Entity
    res = client.get(
        "/api/v1/patients/search?lname=S",
        headers={"X-API-Key": TEST_API_KEY}
    )
    assert res.status_code == 422

    # FName < 2 chars -> 422 Unprocessable Entity
    res_fname = client.get(
        "/api/v1/patients/search?fname=D",
        headers={"X-API-Key": TEST_API_KEY}
    )
    assert res_fname.status_code == 422


def test_api_get_patient_detail():
    mock_service = MagicMock(spec=OpenDentalPatientService)
    mock_service.get_patient_details = AsyncMock(
        return_value={"PatNum": 101, "FName": "Daniel", "LName": "Smith", "WirelessPhone": "9725550199"}
    )

    app.dependency_overrides[get_patient_service] = lambda: mock_service
    client = TestClient(app)

    try:
        res = client.get("/api/v1/patients/101", headers={"X-API-Key": TEST_API_KEY})
        assert res.status_code == 200
        assert res.json()["PatNum"] == 101

        # 404 test
        mock_service.get_patient_details = AsyncMock(return_value=None)
        res_404 = client.get("/api/v1/patients/9999", headers={"X-API-Key": TEST_API_KEY})
        assert res_404.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_cache_stats_and_clear():
    mock_service = MagicMock(spec=OpenDentalPatientService)
    mock_service.get_cache_stats.return_value = {
        "currsize": 5,
        "maxsize": 2000,
        "ttl": 3600,
        "hits": 12,
        "misses": 5,
    }
    mock_service.clear_cache.return_value = {
        "status": "success",
        "message": "Patient caches flushed successfully",
        "cleared_search_entries": 5,
        "cleared_detail_entries": 2,
    }

    app.dependency_overrides[get_patient_service] = lambda: mock_service
    client = TestClient(app)

    try:
        # Stats
        res_stats = client.get("/api/v1/patients/cache/stats", headers={"X-API-Key": TEST_API_KEY})
        assert res_stats.status_code == 200
        assert res_stats.json()["currsize"] == 5

        # Clear
        res_clear = client.post("/api/v1/patients/cache/clear", headers={"X-API-Key": TEST_API_KEY})
        assert res_clear.status_code == 200
        assert res_clear.json()["status"] == "success"
    finally:
        app.dependency_overrides.clear()
