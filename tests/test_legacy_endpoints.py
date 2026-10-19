import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.schemas.report import ReportListResponse

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_legacy_sts_rooms_endpoint_intact():
    from app.api.dependencies import get_sts_room_service
    from app.schemas.sts_room import STSRoomResponse

    mock_sts_service = MagicMock()
    mock_sts_service.create_room = AsyncMock(return_value=STSRoomResponse(
        name="MF-RahulNair-12345678",
        sid="RM_legacy_sid",
        empty_timeout=300,
        max_participants=2,
        num_participants=0,
        metadata="{}",
        livekit_url="wss://legacy.livekit.cloud",
        token="mock_legacy_jwt",
        identity="user-123456",
    ))
    
    app.dependency_overrides[get_sts_room_service] = lambda: mock_sts_service
    try:
        response = client.post(
            "/api/v1/sts/rooms/",
            json={"persona": "default", "language": "en"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "MF-RahulNair-12345678"
        assert data["token"] == "mock_legacy_jwt"
    finally:
        app.dependency_overrides.clear()


def test_legacy_reports_endpoint_intact():
    from app.api.dependencies import get_report_service

    mock_report_service = MagicMock()
    mock_report_service.list_reports = AsyncMock(return_value=ReportListResponse(
        reports=[],
        stats={"total_calls": 0, "avg_score": 0, "readiness": {}}
    ))

    app.dependency_overrides[get_report_service] = lambda: mock_report_service
    try:
        response = client.get("/api/v1/reports/")
        assert response.status_code == 200
        data = response.json()
        assert "reports" in data
        assert "stats" in data
    finally:
        app.dependency_overrides.clear()
