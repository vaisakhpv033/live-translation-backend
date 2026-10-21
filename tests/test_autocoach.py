import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from livekit import api

from app.main import app
from app.schemas.autocoach import (
    AutoCoachSessionCreate,
    AutoCoachSessionResponse,
    AutoCoachTokenRequest,
    AutoCoachReportPayload,
)
from app.services.autocoach_service import (
    LiveKitAutoCoachService,
    _resolve_patient_name,
    _generate_dental_room_name,
)
from app.services.evaluation_service import (
    GeminiEvaluationService,
    GEMINI_QA_REPORT_SCHEMA,
    GEMINI_DENTAL_QA_REPORT_SCHEMA,
    SYSTEM_PROMPT_DENTAL_COACH,
    SYSTEM_PROMPT_SBI,
)
from app.schemas.room import RoomResponse


# ──────────────────────────────────────────────────────────────
#  1. Unit Tests: Patient Resolution & Room Naming
# ──────────────────────────────────────────────────────────────

def test_resolve_patient_name():
    # English names
    assert _resolve_patient_name("en-US", "default", None) == "Mukul Sharma"
    assert _resolve_patient_name("en-US", "skeptical", None) == "David Miller"
    
    # Spanish names
    assert _resolve_patient_name("es-US", "default", None) == "Carlos Rodriguez"
    assert _resolve_patient_name("es-US", "angry", None) == "Hector Ramirez"
    
    # Code-mixed / Spanglish names
    assert _resolve_patient_name("code-mixed", "default", None) == "Maria Gonzalez"
    assert _resolve_patient_name("es-en", "anxious", None) == "Diego Alvarez"
    
    # Custom explicit name override
    assert _resolve_patient_name("en-US", "default", "Dr. Gregory House") == "Dr. Gregory House"


def test_generate_dental_room_name():
    room_name = _generate_dental_room_name("dental_scheduling", "Mukul Sharma")
    assert room_name.startswith("DENTAL-Scheduling-MukulSharma-")


# ──────────────────────────────────────────────────────────────
#  2. Unit Tests: Schemas & Validation
# ──────────────────────────────────────────────────────────────

def test_autocoach_session_create_defaults():
    session = AutoCoachSessionCreate()
    assert session.scenario == "dental_scheduling"
    assert session.language == "en-US"
    assert session.agent_name == "autocoach-customer-sts"
    assert session.wait_timeout_seconds == 10.0


def test_autocoach_session_response_model():
    resp = AutoCoachSessionResponse(
        room_name="DENTAL-Scheduling-Mukul-123456",
        room_sid="RM_test123",
        livekit_url="wss://test.livekit.cloud",
        token="mock_token_jwt",
        identity="trainee-trainee_1",
        agent_status="ready",
        agent_identity="agent-autocoach-1",
        scenario="dental_scheduling",
        language="en-US",
        patient_name="Mukul Sharma",
    )
    assert resp.agent_status == "ready"
    assert resp.token == "mock_token_jwt"


# ──────────────────────────────────────────────────────────────
#  3. Unit Tests: AutoCoach Service Agent-First Handshake
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handshake_success_issues_trainee_token():
    mock_lk = MagicMock()
    
    # Mock room creation
    mock_room_info = MagicMock()
    mock_room_info.name = "DENTAL-Scheduling-MukulSharma-abc123"
    mock_room_info.sid = "RM_abc123"
    mock_room_info.metadata = "{}"
    mock_lk.room.create_room = AsyncMock(return_value=mock_room_info)
    
    # Mock agent dispatch
    mock_lk.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    
    # Mock participant list returning active agent worker
    mock_agent_part = MagicMock()
    mock_agent_part.kind = 2  # ParticipantInfo.Kind.AGENT
    mock_agent_part.identity = "agent-autocoach-sts-01"
    mock_agent_part.name = "autocoach-customer-sts"
    
    mock_part_resp = MagicMock()
    mock_part_resp.participants = [mock_agent_part]
    mock_lk.room.list_participants = AsyncMock(return_value=mock_part_resp)
    
    service = LiveKitAutoCoachService(mock_lk)
    
    session_req = AutoCoachSessionCreate(
        scenario="dental_scheduling",
        language="en-US",
        patient_name="Mukul Sharma",
        wait_timeout_seconds=2.0,
    )
    
    with patch.object(service, "_build_trainee_token", return_value="mock_jwt_trainee_token"):
        result = await service.create_and_dispatch_session(session_req)
        
        assert result.agent_status == "ready"
        assert result.agent_identity == "agent-autocoach-sts-01"
        assert result.token == "mock_jwt_trainee_token"
        assert result.room_name == mock_room_info.name
        
        mock_lk.room.create_room.assert_called_once()
        mock_lk.agent_dispatch.create_dispatch.assert_called_once()


@pytest.mark.asyncio
async def test_handshake_timeout_cleans_up_room_and_raises_504():
    mock_lk = MagicMock()
    
    mock_room_info = MagicMock()
    mock_room_info.name = "DENTAL-Scheduling-Timeout-abc123"
    mock_room_info.sid = "RM_timeout"
    mock_lk.room.create_room = AsyncMock(return_value=mock_room_info)
    mock_lk.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())
    
    # Participants list always returns empty (agent never arrives)
    mock_part_resp = MagicMock()
    mock_part_resp.participants = []
    mock_lk.room.list_participants = AsyncMock(return_value=mock_part_resp)
    mock_lk.room.delete_room = AsyncMock()
    
    service = LiveKitAutoCoachService(mock_lk)
    
    session_req = AutoCoachSessionCreate(
        scenario="dental_scheduling",
        wait_timeout_seconds=1.0,  # valid minimum timeout for test
    )
    
    with pytest.raises(HTTPException) as exc_info:
        await service.create_and_dispatch_session(session_req)
        
    assert exc_info.value.status_code == 504
    assert "Agent dispatch handshake timed out" in exc_info.value.detail
    # Verify cleanup: room was deleted
    mock_lk.room.delete_room.assert_called_once()


# ──────────────────────────────────────────────────────────────
#  4. Unit Tests: Dental Evaluation Schema & Prompt Branching
# ──────────────────────────────────────────────────────────────

def test_dental_schema_structure():
    # Must contain sop_adherence, sop_adherence_summary, and sop_audit_table
    assert "sop_adherence" in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    assert "sop_adherence_summary" in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    assert "sop_audit_table" in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    
    # Must NOT contain product_knowledge or claim_summary
    assert "product_knowledge" not in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    assert "claim_summary" not in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    
    # Verify the 14 dental SOP check fields exist in sop_adherence_summary
    sop_summary_props = GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]["sop_adherence_summary"]["properties"]
    assert "system_down_handling" in sop_summary_props
    assert "spanish_patient_handling" in sop_summary_props
    assert "doctor_request_handling" in sop_summary_props
    assert "note_taking_pause_handling" in sop_summary_props
    assert "patient_moving_handling" in sop_summary_props
    assert "billing_dept_handling" in sop_summary_props
    assert "remote_inquiry_handling" in sop_summary_props
    assert "repeat_offender_handling" in sop_summary_props
    assert "archived_inactive_patient_handling" in sop_summary_props
    assert "balance_due_handling" in sop_summary_props
    assert "xray_transfer_handling" in sop_summary_props
    assert "first_visit_explanation" in sop_summary_props
    assert "urgent_emergency_triage" in sop_summary_props
    assert "overall_sop_verdict" in sop_summary_props

    # Verify sop_audit_table items structure
    audit_item_props = GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]["sop_audit_table"]["items"]["properties"]
    assert "sop_id" in audit_item_props
    assert "sop_title" in audit_item_props
    assert "section" in audit_item_props
    assert "patient_trigger_quote" in audit_item_props
    assert "trainee_actual_quote" in audit_item_props
    assert "verdict" in audit_item_props
    assert "violation_details" in audit_item_props
    assert "approved_sop_verbiage" in audit_item_props


def test_legacy_schema_structure_untouched():
    # Legacy schema retains product_knowledge and claim_summary
    assert "product_knowledge" in GEMINI_QA_REPORT_SCHEMA["properties"]
    assert "claim_summary" in GEMINI_QA_REPORT_SCHEMA["properties"]
    assert "sop_adherence" not in GEMINI_QA_REPORT_SCHEMA["properties"]
    assert "sop_adherence_summary" not in GEMINI_QA_REPORT_SCHEMA["properties"]


def test_format_transcript_dental_roles():
    chat_json = json.dumps({
        "items": [
            {"role": "user", "type": "message", "content": ["Hello, thanks for calling smile dental."]},
            {"role": "assistant", "type": "message", "content": ["Hi, I have a broken tooth."]}
        ]
    })
    
    # Dental formatting
    dental_transcript = GeminiEvaluationService._format_transcript(chat_json, is_dental=True)
    assert "Front Desk Trainee: Hello, thanks for calling smile dental." in dental_transcript
    assert "Patient: Hi, I have a broken tooth." in dental_transcript
    
    # Legacy formatting
    legacy_transcript = GeminiEvaluationService._format_transcript(chat_json, is_dental=False)
    assert "Ira Representative: Hello, thanks for calling smile dental." in legacy_transcript
    assert "AI Customer: Hi, I have a broken tooth." in legacy_transcript


@pytest.mark.asyncio
async def test_evaluate_chat_history_branching():
    eval_service = GeminiEvaluationService()
    
    # Test dental branch selects dental schema and prompt
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": json.dumps({"overall_score": 92, "sop_adherence": {"score": 9, "reason": "Followed verbiage"}})}
                        ]
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        chat_json = json.dumps({"items": []})
        report_card, score = await eval_service.evaluate_chat_history(chat_json, scenario="dental_scheduling")
        
        assert score == 92
        assert report_card["sop_adherence"]["score"] == 9
        
        # Verify the payload sent to Gemini used GEMINI_DENTAL_QA_REPORT_SCHEMA, thinkingConfig, and gemini-3.8-flash
        call_kwargs = mock_post.call_args.kwargs
        call_args = mock_post.call_args.args
        sent_payload = call_kwargs["json"]
        assert sent_payload["generationConfig"]["responseSchema"] == GEMINI_DENTAL_QA_REPORT_SCHEMA
        assert sent_payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}
        assert "gemini-3.8-flash" in (call_args[0] if call_args else call_kwargs.get("url", ""))


# ──────────────────────────────────────────────────────────────
#  5. Integration Tests: API Endpoints via TestClient
# ──────────────────────────────────────────────────────────────

client = TestClient(app)


def test_api_start_session_endpoint():
    from app.api.dependencies import get_autocoach_service
    
    mock_service = MagicMock()
    mock_service.create_and_dispatch_session = AsyncMock(return_value=AutoCoachSessionResponse(
        room_name="DENTAL-Scheduling-MukulSharma-123456",
        room_sid="RM_mock_sid",
        livekit_url="wss://test.livekit.cloud",
        token="mock_token_jwt",
        identity="trainee-trainee_1",
        agent_status="ready",
        agent_identity="agent-autocoach-1",
        scenario="dental_scheduling",
        language="en-US",
        patient_name="Mukul Sharma",
    ))
    
    app.dependency_overrides[get_autocoach_service] = lambda: mock_service
    
    try:
        response = client.post(
            "/api/v1/autocoach/start-session",
            json={
                "scenario": "dental_scheduling",
                "language": "en-US",
                "patient_name": "Mukul Sharma",
                "persona": "default",
                "difficulty": "medium",
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["room_name"] == "DENTAL-Scheduling-MukulSharma-123456"
        assert data["agent_status"] == "ready"
        assert data["token"] == "mock_token_jwt"
    finally:
        app.dependency_overrides.clear()


def test_api_autocoach_report_endpoint():
    from app.api.dependencies import get_report_service
    
    mock_report_service = MagicMock()
    mock_report_service.receive_report = AsyncMock(return_value={"status": "success", "message": "Report received"})
    
    app.dependency_overrides[get_report_service] = lambda: mock_report_service
    
    try:
        response = client.post(
            "/api/v1/autocoach/reports",
            json={
                "job_id": "job_autocoach_123",
                "room_name": "DENTAL-Scheduling-Mukul-123456",
                "started_at": "2026-10-19T10:00:00Z",
                "ended_at": "2026-10-19T10:05:00Z",
                "duration_seconds": 300.0,
                "trainee": {"trainee_id": "trainee_01", "trainee_name": "Jane Doe"},
                "simulation": {"scenario": "dental_scheduling", "persona_name": "Mukul Sharma"},
                "chat_history": [
                    {"role": "user", "type": "message", "content": ["Hello!"]},
                    {"role": "assistant", "type": "message", "content": ["Hi, I need an appointment."]}
                ]
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
    finally:
        app.dependency_overrides.clear()


def test_api_autocoach_list_reports_endpoint():
    from app.api.dependencies import get_report_service
    from app.schemas.report import ReportListResponse, ReportSummary

    mock_report_service = MagicMock()
    mock_report_service.list_autocoach_reports = AsyncMock(return_value=ReportListResponse(
        reports=[
            ReportSummary(
                job_id="job_dental_1",
                room="DENTAL-Scheduling-MukulSharma-123",
                started_at="2026-10-19T10:00:00Z",
                ended_at="2026-10-19T10:05:00Z",
                overall_score=88,
                status="completed",
                customer_name="Mukul Sharma",
                agent_type="AutoCoach STS",
                scenario="dental_scheduling",
                readiness_assessment="Production Ready",
            )
        ],
        stats={
            "total_calls": 1,
            "avg_score": 88,
            "readiness": {
                "Production Ready": 1,
                "Ready With Supervision": 0,
                "Developing": 0,
                "Needs Significant Coaching": 0,
                "Not Ready": 0,
            },
        },
    ))

    app.dependency_overrides[get_report_service] = lambda: mock_report_service

    try:
        response = client.get("/api/v1/autocoach/reports")
        assert response.status_code == 200
        data = response.json()
        assert len(data["reports"]) == 1
        assert data["reports"][0]["job_id"] == "job_dental_1"
        assert data["reports"][0]["scenario"] == "dental_scheduling"
        assert data["stats"]["total_calls"] == 1
        assert data["stats"]["avg_score"] == 88
    finally:
        app.dependency_overrides.clear()


def test_api_autocoach_get_report_endpoint():
    from app.api.dependencies import get_report_service
    from app.schemas.report import ReportDetail

    mock_report_service = MagicMock()
    mock_report_service.get_autocoach_report = AsyncMock(side_effect=lambda job_id: (
        ReportDetail(
            job_id="job_dental_1",
            room="DENTAL-Scheduling-MukulSharma-123",
            started_at="2026-10-19T10:00:00Z",
            ended_at="2026-10-19T10:05:00Z",
            overall_score=90,
            status="completed",
            customer_name="Mukul Sharma",
            agent_type="AutoCoach STS",
            scenario="dental_scheduling",
            chat_history=[],
        ) if job_id == "job_dental_1" else None
    ))

    app.dependency_overrides[get_report_service] = lambda: mock_report_service

    try:
        # Success case
        response = client.get("/api/v1/autocoach/reports/job_dental_1")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "job_dental_1"
        assert data["scenario"] == "dental_scheduling"

        # 404 case for non-existent or legacy report
        response_404 = client.get("/api/v1/autocoach/reports/job_legacy_99")
        assert response_404.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_api_autocoach_status_and_retry_endpoint():
    from app.api.dependencies import get_report_service

    mock_report_service = MagicMock()
    mock_report_service.get_autocoach_report_status = AsyncMock(return_value={"status": "completed"})
    mock_report_service.retry_autocoach_evaluation = AsyncMock(return_value={
        "status": "success",
        "chat_history": "[]",
        "scenario": "dental_emergency_trauma",
    })

    app.dependency_overrides[get_report_service] = lambda: mock_report_service

    try:
        # Status endpoint
        status_resp = client.get("/api/v1/autocoach/reports/job_dental_1/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "completed"

        # Retry endpoint
        retry_resp = client.post("/api/v1/autocoach/reports/job_dental_1/retry")
        assert retry_resp.status_code == 200
        assert retry_resp.json()["status"] == "success"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_report_service_strict_segregation():
    from app.services.report_service import ReportService

    legacy_row = {
        "job_id": "job_legacy_1",
        "room": "MF-RahulNair-123",
        "started_at": "2026-10-19T09:00:00Z",
        "ended_at": "2026-10-19T09:05:00Z",
        "duration_seconds": 300,
        "overall_score": 75,
        "status": "completed",
        "customer_name": "Rahul Nair",
        "agent_type": "STS Agent",
        "scenario": "sbi",
        "summary": json.dumps({"readiness_assessment": "Ready With Supervision"}),
        "chat_history": None,
    }

    dental_row = {
        "job_id": "job_dental_1",
        "room": "DENTAL-Scheduling-MukulSharma-456",
        "started_at": "2026-10-19T10:00:00Z",
        "ended_at": "2026-10-19T10:06:00Z",
        "duration_seconds": 360,
        "overall_score": 94,
        "status": "completed",
        "customer_name": "Mukul Sharma",
        "agent_type": "AutoCoach STS",
        "scenario": "dental_scheduling",
        "summary": json.dumps({"readiness_assessment": "Production Ready"}),
        "chat_history": None,
    }

    mock_repo = MagicMock()
    mock_repo.get_legacy_reports = AsyncMock(return_value=[legacy_row])
    mock_repo.get_autocoach_reports = AsyncMock(return_value=[dental_row])
    mock_repo.get_by_job_id = AsyncMock(side_effect=lambda jid: (
        legacy_row if jid == "job_legacy_1" else (dental_row if jid == "job_dental_1" else None)
    ))
    mock_repo.update_summary = AsyncMock()

    mock_eval = MagicMock()
    service = ReportService(mock_repo, mock_eval)

    # 1. Legacy list should only return legacy row
    legacy_list = await service.list_reports()
    assert len(legacy_list.reports) == 1
    assert legacy_list.reports[0].job_id == "job_legacy_1"
    assert legacy_list.stats["avg_score"] == 75

    # 2. AutoCoach list should only return dental row
    autocoach_list = await service.list_autocoach_reports()
    assert len(autocoach_list.reports) == 1
    assert autocoach_list.reports[0].job_id == "job_dental_1"
    assert autocoach_list.stats["avg_score"] == 94

    # 3. Legacy get_report must return None if job_id is dental
    assert await service.get_report("job_dental_1") is None
    assert (await service.get_report("job_legacy_1")).job_id == "job_legacy_1"

    # 4. AutoCoach get_autocoach_report must return None if job_id is legacy
    assert await service.get_autocoach_report("job_legacy_1") is None
    assert (await service.get_autocoach_report("job_dental_1")).job_id == "job_dental_1"

    # 5. Status segregation
    assert await service.get_report_status("job_dental_1") is None
    assert (await service.get_report_status("job_legacy_1"))["status"] == "completed"
    assert await service.get_autocoach_report_status("job_legacy_1") is None
    assert (await service.get_autocoach_report_status("job_dental_1"))["status"] == "completed"

    # 6. Retry segregation
    retry_legacy_err = await service.retry_evaluation("job_dental_1")
    assert retry_legacy_err["status"] == "error"
    retry_autocoach_err = await service.retry_autocoach_evaluation("job_legacy_1")
    assert retry_autocoach_err["status"] == "error"
    retry_autocoach_ok = await service.retry_autocoach_evaluation("job_dental_1")
    assert retry_autocoach_ok["status"] == "success"
    assert retry_autocoach_ok["scenario"] == "dental_scheduling"

