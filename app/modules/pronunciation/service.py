# SPDX-License-Identifier: MIT
"""Pronunciation service layer with SOLID Dependency Inversion (Local vs Remote)."""

from __future__ import annotations
import asyncio
import io
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np

from .audio_utils import decode_audio_bytes, TARGET_SAMPLE_RATE
from .schemas import (
    PronunciationScoreResponse,
    WordPronunciationScore,
    SoundToWorkOn,
    PhoneticIPABreakdown,
    ProsodyMetrics,
)

logger = logging.getLogger("pronunciation.service")


class BasePronunciationService(ABC):
    """Abstract interface defining the pronunciation scoring contract."""

    @abstractmethod
    async def score_audio(self, audio_bytes: bytes, expected_text: str) -> PronunciationScoreResponse:
        """Score spoken audio against reference text."""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Returns True if the underlying model/service is initialized."""
        pass


class LocalPronunciationService(BasePronunciationService):
    """
    In-process ML scorer. Runs Wav2Vec2 + panphon via thread pool
    (asyncio.to_thread) to ensure the FastAPI event loop is never blocked.
    """

    def __init__(self, device: str = "cpu", max_threads: int = 2):
        self.device = device
        self.max_threads = max_threads
        self._model_loaded = False
        self._lock = asyncio.Lock()
        self._engine = None

    def _ensure_engine_initialized(self):
        """Thread-safe engine warm-up and initialization."""
        if self._model_loaded and self._engine is not None:
            return self._engine

        import torch
        from .engine import speech, config
        from .engine.config import AnalyzerConfig

        # CPU Thread Throttling to protect background tasks on 4 GB servers
        if self.device == "cpu":
            torch.set_num_threads(max(1, self.max_threads))

        logger.info(f"Initializing local Phoneme Engine (device={self.device}, threads={self.max_threads})...")
        config.configure(AnalyzerConfig(device=self.device, espeak_language="en-us"))
        speech.load_models()
        self._engine = speech
        self._model_loaded = True
        return self._engine

    def is_ready(self) -> bool:
        return self._model_loaded

    def warm_up(self):
        """Pre-warm model weights on application startup."""
        try:
            self._ensure_engine_initialized()
            from .engine import speech
            speech.warm_up()
            logger.info("Local phoneme assessment engine pre-warmed successfully.")
        except Exception as e:
            logger.warning(f"Engine pre-warm delayed: {e}. Model will load on first request.")

    def _sync_analyze(self, audio_np: np.ndarray, expected_text: str):
        """Pure synchronous function executed inside asyncio.to_thread."""
        engine = self._ensure_engine_initialized()
        from .engine import prosody

        # 1. Run core articulatory phoneme assessment
        result = engine.analyze(
            user_audio=audio_np,
            expected_text=expected_text,
            user_sr=TARGET_SAMPLE_RATE,
        )

        # 2. Extract pitch (F0) and volume contours
        prosody_info = prosody.extract_audio_prosody(audio_np, TARGET_SAMPLE_RATE)
        return result, prosody_info

    async def score_audio(self, audio_bytes: bytes, expected_text: str) -> PronunciationScoreResponse:
        t_start = time.perf_counter()

        # 1. Decode audio bytes into normalized 16 kHz float32 (in worker thread)
        audio_np, _ = await asyncio.to_thread(decode_audio_bytes, audio_bytes, TARGET_SAMPLE_RATE)

        # 2. Run ML inference in thread pool (PyTorch releases GIL during tensor ops)
        result, prosody_info = await asyncio.to_thread(self._sync_analyze, audio_np, expected_text)

        elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

        # 3. Format per-word ratings & bad words list
        words_list: List[WordPronunciationScore] = []
        raw_bad_words = [str(w) for w in (result.words_with_errors or [])]
        err_words_set = {w.lower().strip(".,!?:;\"'") for w in raw_bad_words}
        bad_words_list: List[str] = list(raw_bad_words)

        for item in (result.reference_words or []):
            word_str = item.get("word", "")
            clean_w = word_str.lower().strip(".,!?:;\"'")
            lvl = item.get("level", "good")
            is_err = (lvl == "bad") or (item.get("correct") is False) or (clean_w in err_words_set)
            
            if is_err:
                score_val = 0.0
                label_val = "Needs work"
                if word_str and clean_w not in {b.lower().strip(".,!?:;\"'") for b in bad_words_list}:
                    bad_words_list.append(word_str)
            elif lvl == "ok":
                score_val = 60.0
                label_val = "Borderline"
            else:
                score_val = 100.0
                label_val = "Good"

            words_list.append(
                WordPronunciationScore(
                    word=word_str,
                    score=score_val,
                    mispronounced=is_err,
                    label=label_val,
                )
            )

        # 4. Format top sounds needing practice
        sounds_list: List[SoundToWorkOn] = []
        for sound in (result.weak_phonemes or []):
            ph = sound.get("phoneme", "")
            if ph:
                if not ph.startswith("/"):
                    ph = f"/{ph}/"
                sounds_list.append(
                    SoundToWorkOn(
                        phoneme=ph,
                        severity=round(float(sound.get("severity", 0.0)), 4),
                        count=int(sound.get("count", 1)),
                    )
                )

        # 5. Format annotated phrase
        annotated_phrase = expected_text
        if result.words_with_errors:
            parts = []
            for token in expected_text.split():
                clean_token = token.strip(".,!?:;\"'").lower()
                if clean_token in err_words_set:
                    parts.append(f"_{token}_")
                else:
                    parts.append(token)
            annotated_phrase = " ".join(parts)

        # 6. Verbal grade & rating label
        raw_score = round(float(result.score), 1)
        grade_str = result.grade if result.grade else (str(result.bucket) if result.bucket >= 0 else "N/A")
        if raw_score >= 80:
            rating_label = "Good"
        elif raw_score >= 60:
            rating_label = "Average (Try Again)"
        else:
            rating_label = "Needs work (Try Again)"

        return PronunciationScoreResponse(
            overall_score=raw_score,
            grade=grade_str,
            rating_label=rating_label,
            passed=bool(result.passed),
            annotated_phrase=annotated_phrase,
            bad_words=bad_words_list,
            words=words_list,
            sounds_to_work_on=sounds_list,
            ipa_breakdown=PhoneticIPABreakdown(
                expected_ipa=" ".join(result.expected_phonemes or []),
                transcribed_ipa=" ".join(result.transcribed_phonemes or []),
            ),
            prosody=ProsodyMetrics(
                pitch_f0_mean=prosody_info.get("pitch_f0_mean", 0.0),
                pitch_f0_std=prosody_info.get("pitch_f0_std", 0.0),
                pitch_f0_range=prosody_info.get("pitch_f0_range", 0.0),
                energy_rms_mean=prosody_info.get("energy_rms_mean", 0.0),
                duration_sec=prosody_info.get("duration_sec", 0.0),
            ),
            processing_time_ms=elapsed_ms,
            backend_mode="local",
        )


class RemotePronunciationService(BasePronunciationService):
    """
    HTTP Proxy client. Forwards scoring requests to a dedicated remote
    microservice URL, allowing instant separation without altering business callers.
    """

    def __init__(self, service_url: str):
        self.service_url = service_url.rstrip("/")
        import httpx
        self._client = httpx.AsyncClient(timeout=30.0)

    def is_ready(self) -> bool:
        return bool(self.service_url)

    async def score_audio(self, audio_bytes: bytes, expected_text: str) -> PronunciationScoreResponse:
        t_start = time.perf_counter()
        url = f"{self.service_url}/api/v1/pronunciation/score"
        files = {"audio_file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav")}
        data = {"expected_text": expected_text}

        resp = await self._client.post(url, files=files, data=data)
        resp.raise_for_status()
        raw = resp.json()
        raw["processing_time_ms"] = round((time.perf_counter() - t_start) * 1000.0, 1)
        raw["backend_mode"] = "remote"
        return PronunciationScoreResponse.model_validate(raw)


# Module-level singleton
_service_instance: Optional[BasePronunciationService] = None


def get_pronunciation_service() -> BasePronunciationService:
    """Dependency provider for FastAPI route endpoints."""
    global _service_instance
    if _service_instance is not None:
        return _service_instance

    # Read configuration dynamically to avoid circular imports
    try:
        from app.core.config import get_settings
        settings = get_settings()
        backend_mode = getattr(settings, "PRONUNCIATION_BACKEND", "local")
        remote_url = getattr(settings, "PRONUNCIATION_SERVICE_URL", "")
        device = getattr(settings, "PRONUNCIATION_DEVICE", "cpu")
        max_threads = getattr(settings, "PRONUNCIATION_MAX_THREADS", 2)
    except Exception:
        backend_mode = "local"
        remote_url = ""
        device = "cpu"
        max_threads = 2

    if backend_mode.lower() == "remote" and remote_url:
        logger.info(f"Using Remote Pronunciation Service at: {remote_url}")
        _service_instance = RemotePronunciationService(remote_url)
    else:
        logger.info(f"Using Local Pronunciation Service (device={device})")
        _service_instance = LocalPronunciationService(device=device, max_threads=max_threads)

    return _service_instance
