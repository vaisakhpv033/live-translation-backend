# SPDX-License-Identifier: MIT
"""Pydantic schemas for Pronunciation Assessment API."""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class SoundToWorkOn(BaseModel):
    """Specific phoneme sound recommended for practice."""
    phoneme: str = Field(..., description="IPA phoneme symbol (e.g. /r/, /θ/, /ɑ/)")
    severity: float = Field(..., description="Error severity rating (0.0 to 1.0, higher is worse)")
    count: int = Field(default=1, description="Number of times this error occurred in the phrase")


class WordPronunciationScore(BaseModel):
    """Word-level pronunciation score and error breakdown."""
    word: str = Field(..., description="Target word from the prompt")
    score: float = Field(..., description="Calculated word-level score (0 to 100)")
    mispronounced: bool = Field(..., description="True if marked as mispronounced")
    label: str = Field(..., description="Human rating label ('Good', 'Average', 'Needs work')")


class PhoneticIPABreakdown(BaseModel):
    """IPA phoneme transcriptions comparing expected native vs learner."""
    expected_ipa: str = Field(..., description="Native target IPA phoneme sequence")
    transcribed_ipa: str = Field(..., description="Spoken learner IPA phoneme sequence recognized from audio")


class ProsodyMetrics(BaseModel):
    """Acoustic prosody, pitch, and energy indicators."""
    pitch_f0_mean: float = Field(default=0.0, description="Mean fundamental pitch in Hz")
    pitch_f0_std: float = Field(default=0.0, description="Pitch variability (standard deviation)")
    pitch_f0_range: float = Field(default=0.0, description="Pitch range (max - min) in Hz")
    energy_rms_mean: float = Field(default=0.0, description="Normalized vocal intensity / volume (0-250)")
    duration_sec: float = Field(default=0.0, description="Duration of speech in seconds")


class PronunciationScoreResponse(BaseModel):
    """Standardized response schema for pronunciation assessment."""
    overall_score: float = Field(..., description="Overall pronunciation score (0.0 to 100.0)")
    grade: str = Field(..., description="Calibrated proficiency grade (0 to 5, e.g. '3', '4+')")
    rating_label: str = Field(..., description="Verbal rating ('Excellent', 'Good', 'Needs work (Try Again)')")
    passed: bool = Field(..., description="True if score passes the threshold")
    annotated_phrase: str = Field(..., description="Prompt phrase with mispronounced words highlighted")
    words: List[WordPronunciationScore] = Field(default_factory=list, description="Per-word pronunciation breakdown")
    sounds_to_work_on: List[SoundToWorkOn] = Field(default_factory=list, description="Top prioritized phonemes needing practice")
    ipa_breakdown: PhoneticIPABreakdown = Field(..., description="Comparison between expected and transcribed IPA")
    prosody: Optional[ProsodyMetrics] = Field(default=None, description="Prosody metrics (pitch and energy)")
    processing_time_ms: float = Field(..., description="Server inference processing duration in milliseconds")
    backend_mode: str = Field(default="local", description="Backend execution mode ('local' or 'remote')")


class HealthStatusResponse(BaseModel):
    """Health check response for pronunciation engine."""
    status: str = Field(default="healthy")
    module: str = Field(default="pronunciation-assessment")
    backend_mode: str = Field(..., description="'local' or 'remote'")
    device: str = Field(..., description="'cpu' or 'cuda'")
    model_loaded: bool = Field(..., description="True if ML weights are initialized in memory")
