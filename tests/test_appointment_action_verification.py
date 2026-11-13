"""
Unit and Integration Tests for Stage 4: Appointment Action Verification.
Verifies:
1. Strict Open Dental READ-ONLY enforcement (GET-only).
2. Slot window boundary matching (start-inclusive, end-exclusive) and provider/clinic scoping.
3. Cancel & Reschedule verdict building (pass / partial / fail).
4. Conditional Stage 4 orchestration and error isolation (Stages 1-3 preserved).
5. End-to-end extra_metadata forwarding from AutoCoach/Reports endpoints -> EvaluationService -> DentalQA.
"""

import json
import pytest
from datetime import date, time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.modules.dental_qa.core.stage4_action_verifier import (
    _assert_readonly_method,
    _parse_date,
    _parse_time,
    _slot_matches_window,
    _strip_json_fences,
    build_verdict,
    verify_appointment_action,
    verify_slots_availability,
)
from app.modules.dental_qa.schemas import (
    AppointmentActionVerdict,
    BehavioralEvaluationResponse,
    CallMetadata,
    ClinicProtocolAuditResponse,
    ComplianceSecurityReview,
    DentalQAReportCard,
    DentalSOPAuditResponse,
    DimensionScore,
    EvaluatedScores,
    QualitativeAnalysis,
    SlotAvailabilityResult,
    SuggestedSlot,
    TranscriptOutcome,
)
from app.modules.dental_qa.service import get_dental_qa_service
from app.main import app
from app.services.background_evaluation import (
    extract_extra_metadata,
    run_background_evaluation,
)
from app.services.evaluation_service import GeminiEvaluationService
from app.services.report_service import ReportService
from app.repositories.report_repository import IReportRepository


# ──────────────────────────────────────────────────────────────
#  1. Read-Only Safeguard & Time/Window Helpers
# ──────────────────────────────────────────────────────────────

def test_readonly_safeguard_blocks_mutations():
    _assert_readonly_method("GET")
    _assert_readonly_method("get")

    for forbidden in ("POST", "PUT", "PATCH", "DELETE"):
        with pytest.raises(PermissionError):
            _assert_readonly_method(forbidden)


def test_parse_time_variants():
    assert _parse_time("09:00") == time(9, 0)
    assert _parse_time("14:30:00") == time(14, 30)
    assert _parse_time("9:15 AM") == time(9, 15)
    assert _parse_time("2:30 pm") == time(14, 30)
    assert _parse_time("not-a-time") is None
    # Model reasoning / commentary leakage recovery
    leaked_1 = "16:00 production/provider null if not mentioned? Yes provider: null, check schema: provider can be string or null provider: null. Let's make it standard: provider: null, time: 16:00"
    leaked_2 = "11:30 production/provider null provider: null"
    assert _parse_time(leaked_1) == time(16, 0)
    assert _parse_time(leaked_2) == time(11, 30)


def test_suggested_slot_sanitizes_leaked_reasoning_and_null_provider():
    slot1 = SuggestedSlot(
        date="2026-11-16",
        time="16:00 production/provider null if not mentioned? Yes provider: null, check schema: provider can be string or null provider: null. Let's make it standard: provider: null, time: 16:00",
        provider="null",
        raw_text="next Monday, 4:00 p.m.",
    )
    assert slot1.time == "16:00"
    assert slot1.provider is None
    assert slot1.date == "2026-11-16"

    slot2 = SuggestedSlot(
        date="2026-11-19",
        time="11:30 production/provider null provider: null",
        provider="Dr. Smith",
        raw_text="11:30 a.m. slot on Thursday",
    )
    assert slot2.time == "11:30"
    assert slot2.provider == "Dr. Smith"
    assert slot2.date == "2026-11-19"


def test_slot_matches_window_boundaries_and_scoping():
    od_slot = {
        "DateTimeStart": "2026-11-20 09:00:00",
        "DateTimeEnd": "2026-11-20 09:30:00",
        "ProvNum": 1,
        "OpNum": 3,
    }
    target_date = date(2026, 11, 20)

    # Start time inclusive, end time exclusive
    assert _slot_matches_window(target_date, time(9, 0), od_slot, 1, {3}) is True
    assert _slot_matches_window(target_date, time(9, 15), od_slot, 1, {3}) is True
    assert _slot_matches_window(target_date, time(9, 30), od_slot, 1, {3}) is False

    # Provider scoping
    assert _slot_matches_window(target_date, time(9, 0), od_slot, 2, {3}) is False

    # Clinic operatory scoping
    assert _slot_matches_window(target_date, time(9, 0), od_slot, 1, {4, 5}) is False


# ──────────────────────────────────────────────────────────────
#  2. Open Dental Slots Verification (Doctor + Clinic Scoping)
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_slots_availability_doctor_and_clinic_scoping():
    slots = [
        SuggestedSlot(date="2026-11-20", time="09:00", raw_text="Nov 20 at 9am"),
        SuggestedSlot(date="2026-11-20", time="14:00", raw_text="Nov 20 at 2pm"),
    ]

    async def fake_get(url, headers=None, params=None):
        resp = MagicMock()
        if url.endswith("/operatories"):
            assert params == {"ClinicNum": 2}
            resp.status_code = 200
            resp.json.return_value = [
                {"OperatoryNum": 3, "ClinicNum": 2, "IsHidden": "false"},
                {"OperatoryNum": 4, "ClinicNum": 2, "IsHidden": "false"},
            ]
            return resp

        if url.endswith("/appointments/Slots"):
            assert params["ProvNum"] == 7
            assert params["date"] == "2026-11-20"
            if params.get("OpNum") == 3:
                resp.status_code = 200
                resp.json.return_value = [
                    {
                        "DateTimeStart": "2026-11-20 09:00:00",
                        "DateTimeEnd": "2026-11-20 10:00:00",
                        "ProvNum": 7,
                        "OpNum": 3,
                    }
                ]
                return resp
            if params.get("OpNum") == 4:
                # 14:00 is not open in any operatory of Clinic 2
                resp.status_code = 200
                resp.json.return_value = []
                return resp

        resp.status_code = 404
        resp.json.return_value = []
        return resp

    with patch("httpx.AsyncClient.get", side_effect=fake_get):
        results = await verify_slots_availability(
            slots=slots,
            prov_num=7,
            op_num=3,
            clinic_num=2,
        )

    assert len(results) == 2
    assert results[0].is_available is True
    assert "ClinicNum=2" in results[0].explanation
    assert results[1].is_available is False


@pytest.mark.asyncio
async def test_verify_slots_clinic_fallback_to_second_operatory():
    slots = [SuggestedSlot(date="2026-11-20", time="11:00", raw_text="11am on Nov 20")]

    async def fake_get(url, headers=None, params=None):
        resp = MagicMock()
        if url.endswith("/operatories"):
            resp.status_code = 200
            resp.json.return_value = [
                {"OperatoryNum": 3, "ClinicNum": 2, "IsHidden": "false"},
                {"OperatoryNum": 4, "ClinicNum": 2, "IsHidden": "false"},
            ]
            return resp
        if url.endswith("/appointments/Slots"):
            if params.get("OpNum") == 3:
                resp.status_code = 200
                resp.json.return_value = []  # Chair 3 booked at 11am
                return resp
            if params.get("OpNum") == 4:
                resp.status_code = 200
                resp.json.return_value = [
                    {
                        "DateTimeStart": "2026-11-20 10:30:00",
                        "DateTimeEnd": "2026-11-20 12:00:00",
                        "ProvNum": 7,
                        "OpNum": 4,
                    }
                ]
                return resp
        resp.status_code = 404
        resp.json.return_value = []
        return resp

    with patch("httpx.AsyncClient.get", side_effect=fake_get):
        results = await verify_slots_availability(
            slots=slots,
            prov_num=7,
            op_num=3,
            clinic_num=2,
        )

    assert len(results) == 1
    assert results[0].is_available is True
    assert results[0].matching_od_slots[0]["OpNum"] == 4


# ──────────────────────────────────────────────────────────────
#  3. Verdict Logic (Cancel & Reschedule)
# ──────────────────────────────────────────────────────────────

def test_build_verdict_cancel_scenarios():
    meta = {"apt_num": 1001, "pat_num": 2002, "pre_call_apt_status": "Scheduled"}

    # Pass
    verdict_pass = build_verdict(
        call_type="cancel",
        extra_metadata=meta,
        transcript_outcome=TranscriptOutcome(
            cancellation_confirmed=True,
            cancellation_reason_captured=True,
            reason_for_cancellation="Travel conflict",
            correct_patient_verified=True,
            correct_appointment_referenced=True,
            summary="Cancelled cleanly.",
        ),
        slot_checks=[],
    )
    assert verdict_pass.verification_status == "pass"
    assert verdict_pass.checks_failed == []

    # Fail when cancellation not confirmed
    verdict_fail = build_verdict(
        call_type="cancel",
        extra_metadata=meta,
        transcript_outcome=TranscriptOutcome(
            cancellation_confirmed=False,
            cancellation_reason_captured=False,
            correct_patient_verified=True,
            correct_appointment_referenced=True,
            summary="Never confirmed cancellation.",
        ),
        slot_checks=[],
    )
    assert verdict_fail.verification_status == "fail"
    assert "cancellation_not_clearly_confirmed" in verdict_fail.checks_failed


def test_build_verdict_reschedule_scenarios():
    meta = {"apt_num": "1001", "pat_num": "2002", "pre_call_apt_datetime": "2026-11-15 09:00:00"}
    slot_ok = SuggestedSlot(date="2026-11-20", time="10:30", raw_text="Nov 20 at 10:30am")
    slot_bad = SuggestedSlot(date="2026-11-20", time="15:00", raw_text="Nov 20 at 3pm")

    # Pass
    v_pass = build_verdict(
        call_type="reschedule",
        extra_metadata=meta,
        transcript_outcome=TranscriptOutcome(
            reschedule_confirmed=True,
            slots_suggested=[slot_ok],
            final_agreed_slot=slot_ok,
            correct_patient_verified=True,
            correct_appointment_referenced=True,
            summary="Rescheduled cleanly.",
        ),
        slot_checks=[SlotAvailabilityResult(suggested_slot=slot_ok, is_available=True)],
    )
    assert v_pass.verification_status == "pass"
    assert v_pass.all_suggested_slots_available is True
    assert v_pass.final_slot_available is True

    # Fail when final agreed slot is NOT available in OD
    v_fail = build_verdict(
        call_type="reschedule",
        extra_metadata=meta,
        transcript_outcome=TranscriptOutcome(
            reschedule_confirmed=True,
            slots_suggested=[slot_ok, slot_bad],
            final_agreed_slot=slot_bad,
            correct_patient_verified=True,
            correct_appointment_referenced=True,
            summary="Agreed on unavailable slot.",
        ),
        slot_checks=[
            SlotAvailabilityResult(suggested_slot=slot_ok, is_available=True),
            SlotAvailabilityResult(suggested_slot=slot_bad, is_available=False),
        ],
    )
    assert v_fail.verification_status == "fail"
    assert v_fail.final_slot_available is False
    assert "final_agreed_slot_NOT_available_in_od" in v_fail.checks_failed


# ──────────────────────────────────────────────────────────────
#  4. Orchestrator Conditional Stage 4 & Service Payload
# ──────────────────────────────────────────────────────────────

def _make_stage1_2_mocks():
    sop_res = DentalSOPAuditResponse(
        dental_sop_adherence_score=9,
        dental_sop_adherence_reason="Followed SOPs",
        sop_audit_table=[],
    )
    clinic_res = ClinicProtocolAuditResponse(
        clinic_protocol_adherence_score=9,
        clinic_protocol_adherence_reason="Followed clinic protocols",
        clinic_audit_table=[],
    )
    behav_res = BehavioralEvaluationResponse(
        rapport_professionalism=DimensionScore(score=9, reason="Warm"),
        discovery_needs_analysis=DimensionScore(score=8, reason="Good"),
        communication_skills=DimensionScore(score=9, reason="Clear"),
        objection_handling=DimensionScore(score=8, reason="Handled well"),
        recommendation_quality=DimensionScore(score=9, reason="Helpful"),
        compliance_ethical_conduct=DimensionScore(score=10, reason="Compliant"),
        closing_effectiveness=DimensionScore(score=9, reason="Confirmed"),
        call_summary="Good call.",
        strengths=["Polite"],
        improvement_opportunities=[],
        missed_opportunities=[],
        compliance_review_security=ComplianceSecurityReview(
            pci_dss_prepayment="OK", hipaa_privacy="OK", security_credentials="OK"
        ),
        coaching_recommendations=[],
        assessment_reasoning_justification="Strong call.",
    )
    usage = {"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 2}
    return sop_res, clinic_res, behav_res, usage


@pytest.mark.asyncio
async def test_orchestrator_skips_stage4_for_non_cancel_reschedule():
    from app.modules.dental_qa.core.orchestrator import evaluate_dental_call

    sop_res, clinic_res, behav_res, usage = _make_stage1_2_mocks()

    with (
        patch("app.modules.dental_qa.core.orchestrator.audit_dental_sops", new=AsyncMock(return_value=(sop_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.audit_clinic_protocols", new=AsyncMock(return_value=(clinic_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.evaluate_behavioral_dimensions", new=AsyncMock(return_value=(behav_res, usage))),
        patch("app.modules.dental_qa.core.stage4_action_verifier.verify_appointment_action", new=AsyncMock()) as mock_stage4,
    ):
        card = await evaluate_dental_call(
            transcript="Front Desk Trainee: Hello!\nPatient: Confirming my visit.",
            extra_metadata={"call_type": "confirm", "apt_num": 1234, "pat_num": 5678},
        )
        mock_stage4.assert_not_called()
        assert card.action_verification is None


@pytest.mark.asyncio
async def test_orchestrator_runs_stage4_and_isolates_errors():
    from app.modules.dental_qa.core.orchestrator import evaluate_dental_call

    sop_res, clinic_res, behav_res, usage = _make_stage1_2_mocks()

    with (
        patch("app.modules.dental_qa.core.orchestrator.audit_dental_sops", new=AsyncMock(return_value=(sop_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.audit_clinic_protocols", new=AsyncMock(return_value=(clinic_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.evaluate_behavioral_dimensions", new=AsyncMock(return_value=(behav_res, usage))),
        patch(
            "app.modules.dental_qa.core.stage4_action_verifier.verify_appointment_action",
            new=AsyncMock(side_effect=RuntimeError("Open Dental unreachable")),
        ),
    ):
        card = await evaluate_dental_call(
            transcript="Front Desk Trainee: Hello!\nPatient: Please reschedule me.",
            extra_metadata={"call_type": "reschedule", "apt_num": "1234", "pat_num": "5678"},
        )
        assert card.scores.overall_score > 0
        assert card.action_verification is not None
        assert card.action_verification.verification_status == "error"
        assert "Open Dental unreachable" in card.action_verification.verification_summary


def test_frontend_payload_includes_action_verification():
    service = get_dental_qa_service()
    verdict = AppointmentActionVerdict(
        call_type="cancel",
        verification_status="pass",
        original_apt_num=1234,
        original_pat_num=5678,
        transcript_outcome=TranscriptOutcome(cancellation_confirmed=True, summary="Done"),
        checks_passed=["cancellation_confirmed_by_both_parties"],
        verification_summary="Trainee confirmed cancellation with the patient.",
    )
    report_card = DentalQAReportCard(
        call_metadata=CallMetadata(job_id="job_1"),
        scores=EvaluatedScores(
            rapport_professionalism=9,
            discovery_needs_analysis=9,
            dental_sop_adherence=9,
            communication_skills=9,
            objection_handling=9,
            recommendation_quality=9,
            compliance_ethical_conduct=9,
            closing_effectiveness=9,
            clinic_protocol_adherence=9,
            overall_score=90,
            readiness_assessment="Production Ready",
        ),
        detailed_analysis=QualitativeAnalysis(
            call_summary="Cancelled.",
            compliance_review_security=ComplianceSecurityReview(
                pci_dss_prepayment="OK", hipaa_privacy="OK", security_credentials="OK"
            ),
            assessment_reasoning_justification="Great.",
        ),
        action_verification=verdict,
    )

    payload = service.to_frontend_payload(report_card)
    assert "appointment_action_verification" in payload
    assert payload["appointment_action_verification"]["verification_status"] == "pass"
    assert payload["appointment_action_verification"]["original_apt_num"] == 1234


# ──────────────────────────────────────────────────────────────
#  5. Pipeline Extra Metadata Extraction & Endpoint Forwarding
# ──────────────────────────────────────────────────────────────

def test_extract_extra_metadata_variants():
    top = json.dumps({"items": [], "extra_metadata": {"call_type": "cancel", "apt_num": 10}})
    nested = json.dumps({"items": [], "metadata": {"extra_metadata": {"call_type": "reschedule", "apt_num": 20}}})

    assert extract_extra_metadata(top) == {"call_type": "cancel", "apt_num": 10}
    assert extract_extra_metadata(nested) == {"call_type": "reschedule", "apt_num": 20}
    assert extract_extra_metadata(nested, {"call_type": "cancel"}) == {"call_type": "cancel"}


def test_autocoach_report_endpoint_forwards_extra_metadata():
    from app.api.dependencies import get_report_service

    client = TestClient(app)
    mock_report_service = MagicMock()
    mock_report_service.receive_report = AsyncMock(return_value={"status": "success"})
    app.dependency_overrides[get_report_service] = lambda: mock_report_service

    extra = {
        "call_type": "reschedule",
        "apt_num": 1234,
        "pat_num": 5678,
        "pre_call_prov_num": 1,
        "pre_call_op": 3,
        "pre_call_clinic_num": 2,
    }

    try:
        with patch("app.api.v1.endpoints.autocoach.run_background_evaluation", new=AsyncMock()) as mock_bg:
            resp = client.post(
                "/api/v1/autocoach/reports",
                json={
                    "job_id": "job_stage4_1",
                    "room_name": "DENTAL-Custom-Test-123",
                    "ended_at": "2026-11-11T10:00:00Z",
                    "simulation": {"scenario": "dental-patient-custom", "persona_name": "Test Patient"},
                    "chat_history": {"items": [{"role": "user", "text": "Hi"}]},
                    "extra_metadata": extra,
                },
            )
            assert resp.status_code == 201
            mock_bg.assert_called_once()
            _, bg_kwargs = mock_bg.call_args
            assert bg_kwargs["extra_metadata"] == extra

            # Confirm extra_metadata was persisted into Report.chat_history for retries
            saved_payload = mock_report_service.receive_report.call_args[0][0]
            assert saved_payload.chat_history["extra_metadata"] == extra
    finally:
        app.dependency_overrides.clear()


def test_autocoach_retry_and_reports_endpoints_forward_extra_metadata():
    from app.api.dependencies import get_report_service

    client = TestClient(app)
    extra = {"call_type": "cancel", "apt_num": 999, "pat_num": 888}
    mock_report_service = MagicMock()
    mock_report_service.retry_autocoach_evaluation = AsyncMock(
        return_value={
            "status": "success",
            "chat_history": json.dumps({"items": [], "extra_metadata": extra}),
            "scenario": "dental-patient-custom",
        }
    )
    mock_report_service.receive_report = AsyncMock(return_value={"status": "success"})
    app.dependency_overrides[get_report_service] = lambda: mock_report_service

    try:
        with patch("app.api.v1.endpoints.autocoach.run_background_evaluation", new=AsyncMock()) as mock_ac_bg:
            retry_resp = client.post("/api/v1/autocoach/reports/job_retry_1/retry")
            assert retry_resp.status_code == 200
            mock_ac_bg.assert_called_once()
            assert mock_ac_bg.call_args.kwargs["extra_metadata"] == extra

        with patch("app.api.v1.endpoints.reports.run_background_evaluation", new=AsyncMock()) as mock_rep_bg:
            rep_resp = client.post(
                "/api/v1/reports/",
                json={
                    "job_id": "job_rep_1",
                    "room_id": "RM_1",
                    "room": "DENTAL-Room-1",
                    "ended_at": "2026-11-11T10:00:00Z",
                    "scenario": "dental_scheduling",
                    "chat_history": {"items": [], "metadata": {"extra_metadata": extra}},
                },
            )
            assert rep_resp.status_code == 201
            mock_rep_bg.assert_called_once()
            assert mock_rep_bg.call_args.kwargs["extra_metadata"] == extra
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_appointment_action_reschedule_e2e_mocked():
    gemini_json = json.dumps({
        "cancellation_confirmed": False,
        "cancellation_reason_captured": False,
        "reschedule_confirmed": True,
        "slots_suggested": [
            {"date": "2026-11-20", "time": "10:30", "provider": "Dr. Gupta", "raw_text": "Nov 20 at 10:30 AM"}
        ],
        "final_agreed_slot": {
            "date": "2026-11-20", "time": "10:30", "provider": "Dr. Gupta", "raw_text": "Nov 20 at 10:30 AM"
        },
        "correct_patient_verified": True,
        "correct_appointment_referenced": True,
        "summary": "Rescheduled patient to Nov 20 at 10:30 AM.",
    })

    async def fake_post(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": gemini_json}]}}]
        }
        return resp

    async def fake_get(url, headers=None, params=None):
        resp = MagicMock()
        if url.endswith("/operatories"):
            resp.status_code = 200
            resp.json.return_value = [{"OperatoryNum": 3, "ClinicNum": 2, "IsHidden": "false"}]
            return resp
        resp.status_code = 200
        resp.json.return_value = [
            {
                "DateTimeStart": "2026-11-20 10:00:00",
                "DateTimeEnd": "2026-11-20 11:00:00",
                "ProvNum": 1,
                "OpNum": 3,
            }
        ]
        return resp

    with (
        patch("httpx.AsyncClient.post", side_effect=fake_post),
        patch("httpx.AsyncClient.get", side_effect=fake_get),
    ):
        verdict = await verify_appointment_action(
            transcript="Front Desk Trainee: Hi! I can move your Nov 15 cleaning to Nov 20 at 10:30 AM.\nPatient: Perfect!",
            call_type="reschedule",
            extra_metadata={
                "call_type": "reschedule",
                "apt_num": 1234,
                "pat_num": 5678,
                "pre_call_apt_status": "Scheduled",
                "pre_call_apt_datetime": "2026-11-15 09:00:00",
                "pre_call_prov_num": 1,
                "pre_call_op": 3,
                "pre_call_clinic_num": 2,
                "pre_call_proc_descript": "D1110 - Prophy",
                "pre_call_prov_abbr": "DRG",
            },
        )

    assert verdict.verification_status == "pass"
    assert verdict.all_suggested_slots_available is True
    assert verdict.final_slot_available is True
    assert len(verdict.slot_checks) == 1
    assert verdict.slot_checks[0].is_available is True


@pytest.mark.asyncio
async def test_evaluation_service_forwards_extra_metadata():
    eval_service = GeminiEvaluationService()
    extra = {"call_type": "cancel", "apt_num": 55, "pat_num": 66}

    with patch(
        "app.modules.dental_qa.service.DentalQAService.evaluate_transcript_payload",
        new=AsyncMock(return_value=({"overall_score": 91}, 91)),
    ) as mock_eval:
        card, score = await eval_service.evaluate_chat_history(
            chat_history_str='{"items": [{"role": "user", "text": "Cancelled"}]}',
            scenario="dental-patient-custom",
            extra_metadata=extra,
        )
        assert score == 91
        mock_eval.assert_called_once()
        assert mock_eval.call_args.kwargs["extra_metadata"] == extra


def test_parse_date_and_strip_fences():
    assert _parse_date("2026-11-20") == date(2026, 11, 20)
    assert _parse_date("2026/11/20") == date(2026, 11, 20)
    assert _parse_date("11/20/2026") == date(2026, 11, 20)
    assert _parse_date("bad-date") is None

    fenced = '```json\n{"cancellation_confirmed": true}\n```'
    assert json.loads(_strip_json_fences(fenced)) == {"cancellation_confirmed": True}


@pytest.mark.asyncio
async def test_verify_slots_stops_fanout_on_400_date_error():
    slots = [SuggestedSlot(date="2020-01-01", time="09:00", raw_text="Jan 1 at 9am")]
    calls = 0

    async def fake_get(url, headers=None, params=None):
        nonlocal calls
        resp = MagicMock()
        if url.endswith("/operatories"):
            resp.status_code = 200
            resp.json.return_value = [
                {"OperatoryNum": 3, "ClinicNum": 2, "IsHidden": "false", "ProvDentist": 1},
                {"OperatoryNum": 4, "ClinicNum": 2, "IsHidden": "false", "ProvDentist": 1},
                {"OperatoryNum": 5, "ClinicNum": 2, "IsHidden": "false", "ProvDentist": 1},
            ]
            return resp
        calls += 1
        resp.status_code = 400
        resp.text = "date must be today or future"
        return resp

    with patch("httpx.AsyncClient.get", side_effect=fake_get):
        results = await verify_slots_availability(slots=slots, prov_num=1, op_num=3, clinic_num=2)

    assert calls == 1  # Should stop immediately after 400 date error instead of calling Op 4 & 5
    assert results[0].is_available is False
    assert "rejected slot query" in results[0].explanation


@pytest.mark.asyncio
async def test_orchestrator_skips_invalid_ids_and_includes_stage4_tokens():
    from app.modules.dental_qa.core.orchestrator import evaluate_dental_call

    sop_res, clinic_res, behav_res, usage = _make_stage1_2_mocks()

    with (
        patch("app.modules.dental_qa.core.orchestrator.audit_dental_sops", new=AsyncMock(return_value=(sop_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.audit_clinic_protocols", new=AsyncMock(return_value=(clinic_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.evaluate_behavioral_dimensions", new=AsyncMock(return_value=(behav_res, usage))),
        patch("app.modules.dental_qa.core.stage4_action_verifier.verify_appointment_action", new=AsyncMock()) as mock_stage4,
    ):
        # Empty / zero IDs must safely skip Stage 4
        card = await evaluate_dental_call(
            transcript="Front Desk Trainee: Hello\nPatient: Cancel please",
            extra_metadata={"call_type": "Cancel", "apt_num": "", "pat_num": 0},
        )
        mock_stage4.assert_not_called()
        assert card.action_verification is None

    # Now verify Stage 4 token usage is summed cleanly when Stage 4 runs
    gemini_json = json.dumps({
        "cancellation_confirmed": True,
        "cancellation_reason_captured": True,
        "reason_for_cancellation": "Out of town",
        "reschedule_confirmed": False,
        "slots_suggested": [],
        "final_agreed_slot": None,
        "correct_patient_verified": True,
        "correct_appointment_referenced": True,
        "summary": "Patient cancelled appointment.",
    })

    async def fake_gemini_post(url, headers=None, json=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": gemini_json}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "thoughtsTokenCount": 10},
        }
        return resp

    with (
        patch("app.modules.dental_qa.core.orchestrator.audit_dental_sops", new=AsyncMock(return_value=(sop_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.audit_clinic_protocols", new=AsyncMock(return_value=(clinic_res, usage))),
        patch("app.modules.dental_qa.core.orchestrator.evaluate_behavioral_dimensions", new=AsyncMock(return_value=(behav_res, usage))),
        patch("httpx.AsyncClient.post", side_effect=fake_gemini_post),
    ):
        card2 = await evaluate_dental_call(
            transcript="Front Desk Trainee: Cancelled.\nPatient: Thanks.",
            extra_metadata={"call_type": "Cancel", "apt_num": "1234", "pat_num": "5678"},
        )
        assert card2.action_verification is not None
        assert card2.action_verification.verification_status == "pass"
        # Base 3 calls: 3*10=30 prompt + 100 stage4 = 130; 3*5=15 cand + 50 stage4 = 65; 3*2=6 thoughts + 10 stage4 = 16
        assert card2.token_usage["prompt_tokens"] == 130
        assert card2.token_usage["candidates_tokens"] == 65
        assert card2.token_usage["thoughts_tokens"] == 16


def test_reschedule_date_only_agreed_slot_flags_missing_time():
    meta = {"apt_num": 1001, "pat_num": 2002}
    vague_slot = SuggestedSlot(date="2026-11-20", time=None, raw_text="Nov 20")

    verdict = build_verdict(
        call_type="reschedule",
        extra_metadata=meta,
        transcript_outcome=TranscriptOutcome(
            reschedule_confirmed=True,
            slots_suggested=[vague_slot],
            final_agreed_slot=vague_slot,
            correct_patient_verified=True,
            correct_appointment_referenced=True,
            summary="Agreed on a day without time.",
        ),
        slot_checks=[SlotAvailabilityResult(suggested_slot=vague_slot, is_available=True)],
    )
    assert verdict.verification_status == "partial"
    assert "final_agreed_slot_missing_date_or_time" in verdict.checks_failed


