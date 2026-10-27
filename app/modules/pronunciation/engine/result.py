# SPDX-License-Identifier: MIT
"""Result type for pronunciation assessment engine."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PronunciationResult:
    """Outcome of one pronunciation comparison."""

    score: float                                  # 0-100 overall pronunciation score
    word_errors: List[Dict[str, Any]]             # per mispronounced word: expected/heard
    prosody: Dict[str, Any]                       # pitch and energy metrics
    transcription: str                            # what the recognizer produced
    passed: bool = False                          # score >= threshold
    feedback: str = ""                            # human-readable summary
    scored: bool = True

    # 0-5 coarse grade
    bucket: int = -1
    user_percent: float = 0.0
    grade: str = ""
    grade_value: float = -1.0

    # Display fields
    words_with_errors: List[str] = field(default_factory=list)
    expected_phonemes: List[str] = field(default_factory=list)
    transcribed_phonemes: List[str] = field(default_factory=list)
    word_diff: List[Dict[str, str]] = field(default_factory=list)
    reference_words: List[Dict[str, Any]] = field(default_factory=list)
    recognized_units: List[Dict[str, Any]] = field(default_factory=list)
    weak_phonemes: List[Dict[str, Any]] = field(default_factory=list)

    # Phoneme diagnostics
    per_phone_distance: float = 0.0
    bad_baseline: float = 0.0
    phoneme_score: float = 0.0
    recall: float = 0.0
    good_anchor: float = 0.0


__all__ = ["PronunciationResult"]
