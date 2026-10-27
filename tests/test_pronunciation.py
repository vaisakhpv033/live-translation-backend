# SPDX-License-Identifier: MIT
"""Unit tests for the isolated pronunciation assessment module."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.modules.pronunciation.schemas import (
    PronunciationScoreResponse,
    WordPronunciationScore,
    SoundToWorkOn,
    PhoneticIPABreakdown,
    ProsodyMetrics,
)
from app.modules.pronunciation.service import get_pronunciation_service

client = TestClient(app)


def test_pronunciation_health():
    """Verify health endpoint of the pronunciation module."""
    response = client.get("/api/v1/pronunciation/health")
    assert response.status_code == 200
    data = response.json()
    assert data["module"] == "pronunciation-assessment"
    assert "backend_mode" in data
    assert "device" in data


def test_pronunciation_demo_ui():
    """Verify demo web tester HTML page renders."""
    response = client.get("/api/v1/pronunciation/demo")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Pronunciation Assessment" in response.text


def test_pronunciation_score_validation_empty_text():
    """Verify validation when expected_text is missing or blank."""
    fake_audio = io.BytesIO(b"RIFF....WAVEfmt ....data....")
    response = client.post(
        "/api/v1/pronunciation/score",
        files={"audio_file": ("test.wav", fake_audio, "audio/wav")},
        data={"expected_text": "   "},
    )
    assert response.status_code == 422


def test_pronunciation_score_with_mocked_service():
    """Verify end-to-end scoring contract with mocked service dependency."""
    mock_service = MagicMock()
    mock_service.score_audio = AsyncMock(
        return_value=PronunciationScoreResponse(
            overall_score=75.5,
            grade="3+",
            rating_label="Average (Try Again)",
            passed=True,
            annotated_phrase="The _weather_ is getting colder.",
            words=[
                WordPronunciationScore(word="The", score=100.0, mispronounced=False, label="Good"),
                WordPronunciationScore(word="weather", score=0.0, mispronounced=True, label="Needs work"),
            ],
            sounds_to_work_on=[
                SoundToWorkOn(phoneme="/ð/", severity=0.65, count=1),
            ],
            ipa_breakdown=PhoneticIPABreakdown(
                expected_ipa="/ð ə w ɛ ð ə/",
                transcribed_ipa="/d ɑ v e d ʌ/",
            ),
            prosody=ProsodyMetrics(
                pitch_f0_mean=145.2,
                pitch_f0_std=12.4,
                pitch_f0_range=45.0,
                energy_rms_mean=110.0,
                duration_sec=2.4,
            ),
            processing_time_ms=180.5,
            backend_mode="local",
        )
    )

    app.dependency_overrides[get_pronunciation_service] = lambda: mock_service
    try:
        fake_audio = io.BytesIO(b"FAKE_AUDIO_BYTES_FOR_MOCK")
        response = client.post(
            "/api/v1/pronunciation/score",
            files={"audio_file": ("sample.wav", fake_audio, "audio/wav")},
            data={"expected_text": "The weather is getting colder."},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["overall_score"] == 75.5
        assert data["grade"] == "3+"
        assert data["rating_label"] == "Average (Try Again)"
        assert len(data["words"]) == 2
        assert data["words"][1]["mispronounced"] is True
        assert data["sounds_to_work_on"][0]["phoneme"] == "/ð/"
        assert data["ipa_breakdown"]["expected_ipa"] == "/ð ə w ɛ ð ə/"
    finally:
        app.dependency_overrides.clear()
