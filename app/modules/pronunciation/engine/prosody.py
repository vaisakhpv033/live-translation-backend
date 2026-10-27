# SPDX-License-Identifier: MIT
"""Prosody extraction (F0 pitch and RMS energy contours)."""

import numpy as np
from .audio import (
    TARGET_SAMPLE_RATE,
    prepare_waveform,
    trim_silence,
)


def extract_f0(audio_waveform: np.ndarray, sr: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Extract fundamental frequency (F0) contour; NaNs -> 0."""
    import librosa
    f0, _, _ = librosa.pyin(audio_waveform, fmin=50, fmax=450, sr=sr)
    return np.nan_to_num(f0)


def extract_energy(audio_waveform: np.ndarray) -> np.ndarray:
    """Extract RMS energy contour, normalized 0-250."""
    import librosa
    from sklearn.preprocessing import MinMaxScaler
    energy = librosa.feature.rms(y=audio_waveform)
    scaler = MinMaxScaler(feature_range=(0, 250))
    return scaler.fit_transform(energy.T).flatten()


def interpolate_f0(f0: np.ndarray) -> np.ndarray:
    """Interpolate zero F0 values to create continuous contour."""
    f0 = np.array(f0)
    mask = f0 > 0
    if not mask.any():
        return f0
    return np.interp(np.arange(len(f0)), np.where(mask)[0], f0[mask])


def extract_audio_prosody(audio: np.ndarray, sr: int) -> dict:
    """Compute pitch (f0) and energy contours for single audio waveform."""
    try:
        clean_wav = trim_silence(prepare_waveform(audio, sr))
        f0 = interpolate_f0(extract_f0(clean_wav, TARGET_SAMPLE_RATE))
        energy = extract_energy(clean_wav)
        
        valid_f0 = [v for v in f0 if v > 0]
        f0_mean = float(np.mean(valid_f0)) if valid_f0 else 0.0
        f0_std = float(np.std(valid_f0)) if valid_f0 else 0.0
        f0_range = float(np.ptp(valid_f0)) if valid_f0 else 0.0
        energy_mean = float(np.mean(energy)) if len(energy) > 0 else 0.0
        duration = float(len(clean_wav) / TARGET_SAMPLE_RATE)

        return {
            "f0": [round(float(v), 2) for v in f0.tolist()],
            "energy": [round(float(v), 2) for v in energy.tolist()],
            "pitch_f0_mean": round(f0_mean, 1),
            "pitch_f0_std": round(f0_std, 1),
            "pitch_f0_range": round(f0_range, 1),
            "energy_rms_mean": round(energy_mean, 1),
            "duration_sec": round(duration, 2),
        }
    except Exception:
        return {
            "f0": [],
            "energy": [],
            "pitch_f0_mean": 0.0,
            "pitch_f0_std": 0.0,
            "pitch_f0_range": 0.0,
            "energy_rms_mean": 0.0,
            "duration_sec": 0.0,
        }
