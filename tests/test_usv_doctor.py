"""Unit and router tests for the dedicated app.modules.usv_doctor module."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.usv_doctor.evaluation import UsvDoctorEvaluationService
from app.modules.usv_doctor.router import (
    _get_livekit_usv_service,
    _get_report_usv_service,
)
from app.modules.usv_doctor.schemas import (
    UsvDoctorSessionCreate,
    UsvDoctorWebhookPayload,
)
from app.modules.usv_doctor.service import UsvDoctorService


@pytest.mark.asyncio
async def test_usv_doctor_session_injects_reporting_and_completes_handshake():
    mock_lk = MagicMock()
    captured_metadata = {}

    async def fake_create_room(req):
        captured_metadata["room"] = json.loads(req.metadata)
        room = MagicMock()
        room.name = req.name
        room.sid = "RM_usv_001"
        return room

    mock_lk.room.create_room = AsyncMock(side_effect=fake_create_room)
    mock_lk.agent_dispatch.create_dispatch = AsyncMock(return_value=MagicMock())

    agent_part = MagicMock()
    agent_part.kind = 2
    agent_part.identity = "agent-ira-01"
    agent_part.name = "ira-voice-agent"
    part_resp = MagicMock()
    part_resp.participants = [agent_part]
    mock_lk.room.list_participants = AsyncMock(return_value=part_resp)

    service = UsvDoctorService(lk_client=mock_lk)
    req = UsvDoctorSessionCreate(
        agent_name="ira-voice-agent",
        scenario="doctor-detailing",
        language="en-IN",
        patient_name="Dr. Arthur Hayes",
        trainee_id="REP-101",
        trainee_name="Rohan",
        extra_metadata={
            "session_config": {
                "version": "1.0",
                "models": {"provider": "gemini", "model": "gemini-3.8-live", "temperature": 0.4},
                "instructions": {"system_prompt": "You are Dr. Arthur Hayes."},
                "voice": {"provider": "gemini", "voice_id": "Charon", "language": "en-IN"},
                "metadata": {"doctor_specialty": "Cardiology"},
            }
        },
    )

    resp = await service.create_and_dispatch_session(req)
    assert resp.room_name.startswith("USV-Cardiology-DrArthurHayes-")
    assert resp.agent_status == "ready"
    assert resp.language == "en-IN"

    reporting = captured_metadata["room"]["reporting"]
    assert reporting["enabled"] is True
    assert reporting["endpoint"]["url"] == "https://translation.vaisakhpv.space/api/v1/usv-doctor/reports"
    assert reporting["security"]["allow_local"] is False
    assert reporting["payload_config"]["include_model_usage"] is True


@pytest.mark.asyncio
async def test_usv_doctor_receive_report_stores_agent_usage_metrics():
    stored_rows = {}

    class FakeRepo:
        async def save_initial_report(self, data):
            stored_rows[data["job_id"]] = data

        async def get_by_job_id(self, job_id):
            return stored_rows.get(job_id)

    service = UsvDoctorService(repository=FakeRepo())
    payload = UsvDoctorWebhookPayload(
        session_id="ses_001",
        job_id="job_usv_123",
        room_name="USV-Cardiology-DrArthurHayes-abc123",
        agent={"name": "ira-voice-agent", "role": "doctor"},
        started_at="2026-11-26T10:00:00Z",
        ended_at="2026-11-26T10:04:00Z",
        duration_seconds=240.4,
        termination_reason="normal",
        chat_history=[
            {"role": "user", "content": "Good morning doctor, I want to discuss Ecosprin Gold."},
            {"role": "assistant", "content": "Tell me about bleeding risk and dual antiplatelet evidence."},
        ],
        model_usage=[
            {
                "type": "llm_usage",
                "model": "gemini-3.8-live-extended-thinking",
                "input_tokens": 1200,
                "input_cached_tokens": 200,
                "input_text_tokens": 300,
                "input_audio_tokens": 900,
                "output_tokens": 450,
                "output_text_tokens": 60,
                "output_audio_tokens": 350,
                "output_reasoning_tokens": 40,
            },
            {
                "type": "llm_usage",
                "model": "gemini-3.8-live",
                "input_tokens": 300,
                "input_audio_tokens": 200,
                "output_tokens": 150,
                "output_audio_tokens": 100,
            },
        ],
        events=[{"type": "participant_joined"}],
        metadata={
            "scenario": "doctor-detailing",
            "title": "Dr. Arthur Hayes — Interventional Cardiology",
            "doctor_name": "Dr. Arthur Hayes",
            "doctor_specialty": "Cardiology",
            "demeanor": "Skeptical & Evidence-Driven",
            "current_standard_of_care": "Triple therapy for HFrEF",
            "trainee_name": "Rohan",
            "trainee_id": "REP-101",
            "model_name": "gemini-3.8-live",
            "language": "en-IN",
            "voice_id": "Charon",
        },
    )

    ack = await service.receive_report(payload)
    assert ack["status"] == "success"

    saved = stored_rows["job_usv_123"]
    assert saved["duration_seconds"] == 240
    assert saved["agent_input_tokens"] == 1500
    assert saved["agent_input_cached_tokens"] == 200
    assert saved["agent_input_text_tokens"] == 400
    assert saved["agent_input_audio_tokens"] == 1100
    assert saved["agent_output_tokens"] == 600
    assert saved["agent_output_text_tokens"] == 110
    assert saved["agent_output_audio_tokens"] == 450
    assert saved["agent_reasoning_tokens"] == 40
    assert saved["agent_total_tokens"] == 2100
    # Cost check: text_in=400 ($0.75/1M) + audio_in=1100 ($3/1M) + audio_out=450 ($12/1M) + text_out=150 ($4.50/1M)
    assert saved["agent_cost_usd"] == pytest.approx(0.009675, abs=1e-6)
    assert saved["total_cost_usd"] == pytest.approx(0.009675, abs=1e-6)
    assert saved["doctor_specialty"] == "Cardiology"
    assert saved["language"] == "en-IN"


@pytest.mark.asyncio
async def test_usv_doctor_evaluation_persists_qa_score_and_usage_metrics():
    saved_row = {
        "job_id": "job_eval_1",
        "agent_cost_usd": 0.01,
        "chat_history": json.dumps({
            "items": [
                {"role": "user", "content": "Doctor, Ecosprin Gold combines aspirin, clopidogrel, and atorvastatin."},
                {"role": "assistant", "content": "What about GI bleeding risk and muscle pain monitoring?"},
                {"role": "user", "content": "Bleeding risk is key with dual antiplatelets, and monitor LFTs/myalgia."},
            ]
        }),
        "session_metadata": json.dumps({
            "doctor_name": "Dr. Arthur Hayes",
            "doctor_specialty": "Cardiology",
            "clinic_setting": "Heart clinic",
            "demeanor": "Skeptical",
            "current_standard_of_care": "Aspirin + statin",
            "trainee_name": "Rohan",
            "language": "en-IN",
        }),
    }
    captured_update = {}

    class FakeRepo:
        async def get_by_job_id(self, job_id):
            return saved_row if job_id == "job_eval_1" else None

        async def update_evaluation(self, **kwargs):
            captured_update.update(kwargs)

    fake_card = {
        "scenario_practiced": "Cardiology detailing of Ecosprin Gold",
        "overall_score": 84,
        "rapport": {"score": 8, "reason": "Respectful opening"},
        "discovery": {"score": 8, "reason": "Checked standard of care"},
        "product_knowledge": {"score": 9, "reason": "Accurate composition"},
        "communication": {"score": 8, "reason": "Clear"},
        "objection_handling": {"score": 8, "reason": "Addressed bleeding risk"},
        "recommendation_quality": {"score": 8, "reason": "Relevant positioning"},
        "compliance": {"score": 9, "reason": "Honest fair balance"},
        "closing": {"score": 8, "reason": "Clear next step"},
        "positives": ["Transparent fair balance"],
        "improvement_areas": [],
        "missed_opportunities": [],
        "compliance_issues": [],
        "coaching_recommendations": ["Probe adherence earlier"],
        "readiness_assessment": "Production Ready",
        "readiness_reasoning": "Strong scientific and UCPMP compliance.",
    }

    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(fake_card)}]}}],
        "usageMetadata": {
            "promptTokenCount": 1000,
            "cachedContentTokenCount": 400,
            "candidatesTokenCount": 310,
            "thoughtsTokenCount": 90,
            "totalTokenCount": 1400,
        },
    }

    with patch("app.modules.usv_doctor.evaluation.settings", SimpleNamespace(
        GEMINI_API_KEY="test-key",
        GEMINI_EVALUATION_MODEL="gemini-4-hydrogen",
        GEMINI_EVALUATION_THINKING_LEVEL="low",
    )):
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_http_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            service = UsvDoctorService(
                repository=FakeRepo(),
                evaluation_service=UsvDoctorEvaluationService(),
            )
            await service.evaluate_and_update("job_eval_1")

            # Verify Gemini 4 Hydrogen + low thinkingLevel sent in request payload
            call_args = mock_client.post.call_args
            assert "gemini-4-hydrogen:generateContent" in call_args.args[0]
            assert call_args.kwargs["json"]["generationConfig"]["thinkingConfig"] == {
                "thinkingLevel": "low"
            }

    assert captured_update["status"] == "completed"
    assert captured_update["overall_score"] == 84
    assert captured_update["readiness_assessment"] == "Production Ready"
    assert captured_update["qa_model_name"] == "gemini-4-hydrogen"
    assert captured_update["qa_prompt_tokens"] == 1000
    assert captured_update["qa_cached_tokens"] == 400
    assert captured_update["qa_candidates_tokens"] == 310
    assert captured_update["qa_thoughts_tokens"] == 90
    assert captured_update["qa_total_tokens"] == 1400
    # QA cost: uncached_in=600 ($1.50/1M)=0.0009 + cached=400 ($0.075/1M)=0.00003 + out=400 ($7.50/1M)=0.003 => 0.00393
    assert captured_update["qa_cost_usd"] == pytest.approx(0.00393, abs=1e-6)
    assert captured_update["total_cost_usd"] == pytest.approx(0.01393, abs=1e-6)


def test_usv_doctor_router_endpoints_end_to_end():
    fake_db = {
        "job_router_1": {
            "job_id": "job_router_1",
            "session_id": "ses_r1",
            "room_name": "USV-Cardiology-DrHayes-123456",
            "agent_name": "ira-voice-agent",
            "agent_role": "doctor",
            "started_at": "2026-11-26T10:00:00Z",
            "ended_at": "2026-11-26T10:03:00Z",
            "duration_seconds": 180,
            "termination_reason": "normal",
            "status": "completed",
            "scenario": "doctor-detailing",
            "doctor_name": "Dr. Arthur Hayes",
            "doctor_specialty": "Cardiology",
            "trainee_name": "Rohan",
            "trainee_id": "REP-101",
            "chat_history": json.dumps({"items": [{"role": "user", "content": "Hello doctor"}]}),
            "summary": json.dumps({"overall_score": 88, "readiness_assessment": "Production Ready"}),
            "overall_score": 88,
            "readiness_assessment": "Production Ready",
            "agent_input_tokens": 500,
            "agent_output_tokens": 200,
            "agent_input_audio_tokens": 400,
            "agent_output_audio_tokens": 150,
            "agent_total_tokens": 700,
            "qa_model_name": "gemini-3.8-flash",
            "qa_prompt_tokens": 300,
            "qa_candidates_tokens": 120,
            "qa_thoughts_tokens": 40,
            "qa_total_tokens": 460,
        }
    }

    class FakeRepo:
        async def save_initial_report(self, data):
            fake_db[data["job_id"]] = data

        async def get_all(self):
            return list(fake_db.values())

        async def get_by_job_id(self, job_id):
            return fake_db.get(job_id)

        async def reset_for_retry(self, job_id):
            if job_id in fake_db:
                fake_db[job_id]["status"] = "ongoing"
                return fake_db[job_id]
            return None

    fake_service = UsvDoctorService(repository=FakeRepo())
    app.dependency_overrides[_get_report_usv_service] = lambda: fake_service
    try:
        client = TestClient(app, raise_server_exceptions=False)

        list_res = client.get("/api/v1/usv-doctor/reports")
        assert list_res.status_code == 200
        body = list_res.json()
        assert body["stats"]["total_calls"] == 1
        assert body["stats"]["total_agent_tokens"] == 700
        assert body["stats"]["total_qa_tokens"] == 460

        detail_res = client.get("/api/v1/usv-doctor/reports/job_router_1")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["agent_usage"]["total_tokens"] == 700
        assert detail["qa_usage"]["total_tokens"] == 460
        assert detail["chat_history"][0]["role"] == "user"

        with patch("app.modules.usv_doctor.router.run_usv_doctor_background_evaluation") as mock_bg:
            post_res = client.post(
                "/api/v1/usv-doctor/reports",
                json={
                    "job_id": "job_router_2",
                    "room_name": "USV-Cardiology-DrHayes-999999",
                    "ended_at": "2026-11-26T10:05:00Z",
                    "chat_history": [{"role": "user", "content": "Hi"}],
                    "model_usage": [{"input_tokens": 100, "output_tokens": 50}],
                    "metadata": {"doctor_name": "Dr. Hayes", "trainee_name": "Rohan"},
                },
            )
            assert post_res.status_code == 201
            assert fake_db["job_router_2"]["agent_total_tokens"] == 150
            assert mock_bg.called
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_recover_stuck_reports_picks_up_usv_doctor_ongoing_jobs():
    from contextlib import asynccontextmanager
    from app.services import background_evaluation

    @asynccontextmanager
    async def fake_session_factory():
        yield MagicMock()

    mock_legacy_repo = MagicMock()
    mock_legacy_repo.get_ongoing_reports = AsyncMock(return_value=[])

    mock_usv_repo = MagicMock()
    mock_usv_repo.get_ongoing_reports = AsyncMock(
        return_value=[{"job_id": "job_usv_stuck_1", "created_at": "2020-01-01T00:00:00Z"}]
    )

    with patch.object(background_evaluation.db, "_async_session_factory", fake_session_factory):
        with patch.object(background_evaluation, "SQLAlchemyReportRepository", return_value=mock_legacy_repo):
            with patch("app.modules.usv_doctor.repository.UsvDoctorReportRepository", return_value=mock_usv_repo):
                with patch.object(background_evaluation, "run_usv_doctor_background_evaluation") as mock_runner:
                    with patch.object(background_evaluation.asyncio, "create_task") as mock_create_task:
                        await background_evaluation.recover_stuck_reports(threshold_seconds=300)
                        assert mock_runner.called
                        mock_runner.assert_called_once_with("job_usv_stuck_1")
                        assert mock_create_task.called


def test_qa_defaults_and_pricing_calculator():
    from app.core.config import Settings
    from app.modules.dental_qa.config import settings as dental_settings
    from app.modules.usv_doctor.pricing import compute_agent_usage_cost_usd, compute_qa_cost_usd

    assert Settings.model_fields["GEMINI_EVALUATION_MODEL"].default == "gemini-4-hydrogen"
    assert Settings.model_fields["GEMINI_EVALUATION_THINKING_LEVEL"].default == "low"
    assert dental_settings.GEMINI_THINKING_LEVEL == "low"

    # Voice agent pricing (no double counting of reasoning/cached tokens)
    agent_cost = compute_agent_usage_cost_usd(
        [
            {
                "model": "gemini-3.8-live",
                "input_tokens": 1_000_000,
                "input_text_tokens": 200_000,
                "input_audio_tokens": 800_000,
                "input_cached_tokens": 100_000,
                "output_tokens": 1_000_000,
                "output_audio_tokens": 900_000,
                "output_text_tokens": 50_000,
                "output_reasoning_tokens": 50_000,
            }
        ]
    )
    # text_in: 0.2*0.75=0.15 + audio_in: 0.8*3.0=2.40 + audio_out: 0.9*12.0=10.80 + text_out: 0.1*4.50=0.45 => 13.80
    assert agent_cost == pytest.approx(13.80, abs=1e-6)

    # QA Hydrogen pricing with cached tokens + thoughts
    qa_cost = compute_qa_cost_usd(
        model_name="gemini-4-hydrogen",
        prompt_tokens=1_000_000,
        cached_tokens=500_000,
        candidates_tokens=100_000,
        thoughts_tokens=100_000,
    )
    # uncached_in: 0.5*1.50=0.75 + cached_in: 0.5*0.075=0.0375 + out: 0.2*7.50=1.50 => 2.2875
    assert qa_cost == pytest.approx(2.2875, abs=1e-6)


