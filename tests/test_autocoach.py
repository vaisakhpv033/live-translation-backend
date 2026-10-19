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
    # Must contain sop_adherence and sop_adherence_summary
    assert "sop_adherence" in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    assert "sop_adherence_summary" in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    
    # Must NOT contain product_knowledge or claim_summary
    assert "product_knowledge" not in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    assert "claim_summary" not in GEMINI_DENTAL_QA_REPORT_SCHEMA["properties"]
    
    # Verify the 14 dental SOP check fields exist
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
        
        # Verify the payload sent to Gemini used GEMINI_DENTAL_QA_REPORT_SCHEMA
        call_kwargs = mock_post.call_args.kwargs
        sent_payload = call_kwargs["json"]
        assert sent_payload["generationConfig"]["responseSchema"] == GEMINI_DENTAL_QA_REPORT_SCHEMA


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
