# SPDX-License-Identifier: MIT
"""Robust in-memory audio decoding for pronunciation assessment."""

from __future__ import annotations
import io
import logging
import subprocess
from typing import Tuple

import numpy as np
import soundfile as sf

logger = logging.getLogger("pronunciation.audio_utils")
TARGET_SAMPLE_RATE = 16_000


def decode_audio_bytes(raw_bytes: bytes, target_sr: int = TARGET_SAMPLE_RATE) -> Tuple[np.ndarray, int]:
    """
    Decodes audio bytes into a 16 kHz mono float32 NumPy array.
    Supports WAV, FLAC, WebM (Opus), MP3, AAC, and OGG.
    """
    if not raw_bytes or len(raw_bytes) < 16:
        raise ValueError("Audio file payload is empty or too short.")

    # 1. First attempt: standard libsndfile decoding (fast for WAV/FLAC/OGG)
    try:
        data, sr = sf.read(io.BytesIO(raw_bytes), dtype="float32")
        if data.ndim > 1:
            data = data.mean(axis=1)  # downmix to mono
        if sr != target_sr:
            import librosa
            data = librosa.resample(data, orig_sr=sr, target_sr=target_sr)
            sr = target_sr
        return np.ascontiguousarray(data, dtype=np.float32), sr
    except Exception as sf_err:
        logger.debug(f"libsndfile decode failed ({sf_err}), attempting ffmpeg pipe fallback...")

    # 2. Fallback: stream through ffmpeg pipe (handles browser WebM/Opus, M4A, AAC)
    try:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "-ac", "1",
            "-ar", str(target_sr),
            "pipe:1"
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        out_pcm, err = proc.communicate(input=raw_bytes)
        if proc.returncode != 0:
            err_msg = err.decode(errors="ignore") if err else "Unknown ffmpeg error"
            raise RuntimeError(f"FFmpeg transcode failed (exit {proc.returncode}): {err_msg}")

        audio_np = np.frombuffer(out_pcm, dtype=np.float32)
        if audio_np.size == 0:
            raise ValueError("Decoded audio stream contains 0 samples.")
        return np.ascontiguousarray(audio_np, dtype=np.float32), target_sr

    except FileNotFoundError:
        raise RuntimeError(
            "Neither libsndfile nor 'ffmpeg' could decode the uploaded audio. "
            "Please upload standard WAV audio or ensure 'ffmpeg' is installed on the host."
        )
