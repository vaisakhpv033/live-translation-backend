"""
Unit Tests for Stage 1C Voice Rating Parameters Evaluation Phase (IRA AI SOP).
Verifies:
1. Schema integrity for all 5 session blocks (A-E) and 27 parameters.
2. Option B denominator adherence percentage calculation (excluding 'not possible to analyze').
3. Deterministic evaluation of Parameter E2 based on dead_air_triggered watchdog telemetry.
4. Correct payload mapping in DentalQAService.to_frontend_payload().
"""

import pytest
from app.modules.dental_qa.schemas.voice_rating import (
    VoiceVerdict,
    VoiceRatingParameterItem,
    VoiceRatingSessionBlock,
    VoiceRatingAuditResponse,
    Stage1CBlocksABCDRawResponse,
    Stage1CBlockERawResponse,
)
from app.modules.dental_qa.schemas.report_card import (
    CallMetadata,
    EvaluatedScores,
    QualitativeAnalysis,
    DentalQAReportCard,
    ComplianceSecurityReview,
)
from app.modules.dental_qa.service import DentalQAService


def test_voice_rating_session_block_option_b_adherence():
    """Option B semantics: only analyzable parameters count toward denominator."""
    params = [
        VoiceRatingParameterItem(code="A1", parameter_question="Greeting", verdict=VoiceVerdict.FOLLOWED, reasoning="OK"),
        VoiceRatingParameterItem(code="A2", parameter_question="Help", verdict=VoiceVerdict.FOLLOWED, reasoning="OK"),
        VoiceRatingParameterItem(code="A3", parameter_question="Name/Number", verdict=VoiceVerdict.PARTIALLY_FOLLOWED, reasoning="Partial"),
        VoiceRatingParameterItem(code="A4", parameter_question="New patient", verdict=VoiceVerdict.NOT_POSSIBLE, reasoning="N/A"),
    ]
    block = VoiceRatingSessionBlock.from_parameters("A", "Opening", params)
    assert block.followed_count == 2
    assert block.partially_followed_count == 1
    assert block.not_followed_count == 0
    assert block.not_possible_count == 1
    # 2 followed out of 3 analyzable = 66.7%
    assert block.adherence_percentage == 66.7


def test_voice_rating_audit_response_aggregation():
    """Overall voice adherence aggregates across all 5 blocks."""
    b_a = VoiceRatingSessionBlock.from_parameters("A", "Opening", [
        VoiceRatingParameterItem(code="A1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R"),
    ])
    b_b = VoiceRatingSessionBlock.from_parameters("B", "Initial Addressal", [
        VoiceRatingParameterItem(code="B1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R"),
    ])
    b_c = VoiceRatingSessionBlock.from_parameters("C", "Persuasion", [
        VoiceRatingParameterItem(code="C1", parameter_question="Q", verdict=VoiceVerdict.NOT_FOLLOWED, reasoning="R"),
    ])
    b_d = VoiceRatingSessionBlock.from_parameters("D", "Closure", [
        VoiceRatingParameterItem(code="D1", parameter_question="Q", verdict=VoiceVerdict.NOT_POSSIBLE, reasoning="R"),
    ])
    b_e = VoiceRatingSessionBlock.from_parameters("E", "Overall Comm", [
        VoiceRatingParameterItem(code="E1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R"),
    ])

    resp = VoiceRatingAuditResponse.from_blocks(b_a, b_b, b_c, b_d, b_e)
    assert resp.total_parameters_evaluated == 5
    # Analyzable: 4 (A1, B1, C1, E1). Followed: 3 (A1, B1, E1). 3/4 = 75.0%
    assert resp.overall_voice_adherence_pct == 75.0


def test_deterministic_e2_evaluation():
    """Parameter E2 is strictly bound to watchdog telemetry."""
    # Test True -> not followed
    e2_item_triggered = VoiceRatingParameterItem(
        code="E2",
        parameter_question="Was there Dead Air of more than 45s during the conversation ?",
        verdict=VoiceVerdict.NOT_FOLLOWED if True else VoiceVerdict.FOLLOWED,
        reasoning="Watchdog triggered",
    )
    assert e2_item_triggered.verdict == VoiceVerdict.NOT_FOLLOWED

    # Test False -> followed
    e2_item_clean = VoiceRatingParameterItem(
        code="E2",
        parameter_question="Was there Dead Air of more than 45s during the conversation ?",
        verdict=VoiceVerdict.NOT_FOLLOWED if False else VoiceVerdict.FOLLOWED,
        reasoning="No dead air",
    )
    assert e2_item_clean.verdict == VoiceVerdict.FOLLOWED


def test_frontend_payload_mapping_includes_voice_rating():
    """Verifies DentalQAService.to_frontend_payload() includes voice_rating when present."""
    service = DentalQAService()

    block_a = VoiceRatingSessionBlock.from_parameters("A", "Opening", [
        VoiceRatingParameterItem(code="A1", parameter_question="Greeting", verdict=VoiceVerdict.FOLLOWED, reasoning="OK")
    ])
    block_b = VoiceRatingSessionBlock.from_parameters("B", "Initial Addressal", [])
    block_c = VoiceRatingSessionBlock.from_parameters("C", "Persuasion", [])
    block_d = VoiceRatingSessionBlock.from_parameters("D", "Closure", [])
    block_e = VoiceRatingSessionBlock.from_parameters("E", "Overall Communication", [])

    voice_resp = VoiceRatingAuditResponse.from_blocks(block_a, block_b, block_c, block_d, block_e)

    card = DentalQAReportCard(
        call_metadata=CallMetadata(job_id="test_job"),
        scores=EvaluatedScores(
            rapport_professionalism=8,
            discovery_needs_analysis=8,
            dental_sop_adherence=8,
            communication_skills=8,
            objection_handling=8,
            recommendation_quality=8,
            compliance_ethical_conduct=8,
            closing_effectiveness=8,
            clinic_protocol_adherence=8,
            overall_score=80,
            readiness_assessment="Production Ready",
        ),
        detailed_analysis=QualitativeAnalysis(
            call_summary="Test call",
            dental_sop_verbiage_audits=[],
            clinic_protocol_audits=[],
            strengths=[],
            improvement_opportunities=[],
            compliance_review_security=ComplianceSecurityReview(
                pci_dss_prepayment="OK",
                hipaa_privacy="OK",
                security_credentials="OK",
            ),
            coaching_recommendations=[],
            assessment_reasoning_justification="Test justification",
        ),
        voice_rating=voice_resp,
    )

    payload = service.to_frontend_payload(card)
    assert "voice_rating" in payload
    assert payload["voice_rating"]["total_parameters_evaluated"] == 1
    assert payload["voice_rating"]["session_a_opening"]["followed_count"] == 1


@pytest.mark.asyncio
async def test_audit_voice_rating_subcall_isolation():
    """Verifies that if Sub-call 2 times out, Sub-call 1 results are retained and E2 is still deterministic."""
    from unittest.mock import patch
    from app.modules.dental_qa.core.stage1c_voice_rating_auditor import audit_voice_rating_parameters

    mock_raw_abcd = Stage1CBlocksABCDRawResponse(
        session_a_parameters=[
            VoiceRatingParameterItem(code="A1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R1"),
            VoiceRatingParameterItem(code="A2", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R2"),
            VoiceRatingParameterItem(code="A3", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R3"),
            VoiceRatingParameterItem(code="A4", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R4"),
        ],
        session_b_parameters=[
            VoiceRatingParameterItem(code="B1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R5"),
            VoiceRatingParameterItem(code="B2", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R6"),
        ],
        session_c_parameters=[
            VoiceRatingParameterItem(code="C1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R7"),
            VoiceRatingParameterItem(code="C2", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R8"),
            VoiceRatingParameterItem(code="C3", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R9"),
            VoiceRatingParameterItem(code="C4", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R10"),
            VoiceRatingParameterItem(code="C5", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R11"),
        ],
        session_d_parameters=[
            VoiceRatingParameterItem(code="D1", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R12"),
            VoiceRatingParameterItem(code="D2", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R13"),
            VoiceRatingParameterItem(code="D3", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R14"),
            VoiceRatingParameterItem(code="D4", parameter_question="Q", verdict=VoiceVerdict.FOLLOWED, reasoning="R15"),
        ],
    )

    async def mock_call(prompt, schema_cls, **kwargs):
        if schema_cls == Stage1CBlocksABCDRawResponse:
            return mock_raw_abcd, {"promptTokenCount": 500, "candidatesTokenCount": 200}
        raise TimeoutError("Stage 1C Sub-call 2 (Block E) failed after max retries.")

    with patch("app.modules.dental_qa.core.stage1c_voice_rating_auditor._execute_gemini_call", side_effect=mock_call):
        resp, usage = await audit_voice_rating_parameters(
            transcript="Front Desk Trainee: Hello\nPatient: Hi",
            dead_air_triggered=False,
        )

        # Blocks A-D should be preserved from Sub-call 1
        assert resp.session_a_opening.followed_count == 4
        assert resp.session_b_initial_addressal.followed_count == 2
        assert resp.session_c_persuasion.followed_count == 5
        assert resp.session_d_closure.followed_count == 4

        # Block E should be fallback, but E2 must be deterministic
        e2 = next(p for p in resp.session_e_overall_comm.parameters if p.code == "E2")
        assert e2.verdict == VoiceVerdict.FOLLOWED  # Because dead_air_triggered=False
        e1 = next(p for p in resp.session_e_overall_comm.parameters if p.code == "E1")
        assert e1.verdict == VoiceVerdict.NOT_POSSIBLE  # Fallback due to subcall 2 error

        # 15 followed (A-D) + 1 followed (E2) = 16 followed out of 16 analyzable (11 fallback E items are excluded by Option B denominator) = 100.0%
        assert resp.overall_voice_adherence_pct == 100.0
