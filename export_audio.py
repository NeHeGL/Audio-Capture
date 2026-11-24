"""Export trimmed audio via libsndfile (soundfile)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SOUNDFILE_EXPORTS: dict[str, tuple[str, str]] = {
    "wav": ("WAV", "PCM_16"),
    "wave": ("WAV", "PCM_16"),
    "ogg": ("OGG", "VORBIS"),
    "oga": ("OGG", "VORBIS"),
    "flac": ("FLAC", "PCM_16"),
    "mp3": ("MP3", "MPEG_LAYER_III"),
    "aiff": ("AIFF", "PCM_16"),
    "aif": ("AIFF", "PCM_16"),
    "au": ("AU", "PCM_16"),
}

SAVE_FILETYPES: list[tuple[str, str]] = [
    ("WAV audio", "*.wav"),
    ("OGG Vorbis", "*.ogg"),
    ("Ogg audio", "*.oga"),
    ("FLAC", "*.flac"),
    ("MP3", "*.mp3"),
    ("AIFF", "*.aiff"),
    ("Sun/NeXT AU", "*.au"),
    ("All files", "*.*"),
]


def trim_audio(
    samples: np.ndarray,
    sample_rate: int,
    start_sec: float,
    end_sec: float,
) -> np.ndarray:
    if samples.size == 0:
        return samples
    n = samples.shape[0]
    start_i = max(0, int(start_sec * sample_rate))
    end_i = min(n, int(end_sec * sample_rate))
    if end_i <= start_i:
        return np.zeros((0, samples.shape[1] if samples.ndim > 1 else 1), dtype=np.float32)
    return samples[start_i:end_i]


def _to_mono_stereo(samples: np.ndarray) -> np.ndarray:
    if samples.ndim == 1:
        return samples.reshape(-1, 1)
    return samples


def export_file(
    path: Path,
    samples: np.ndarray,
    sample_rate: int,
    fmt: str,
    start_sec: float,
    end_sec: float,
) -> None:
    trimmed = trim_audio(samples, sample_rate, start_sec, end_sec)
    if trimmed.size == 0:
        raise ValueError("Nothing to export — record audio or widen the trim range.")
    ext = path.suffix.lower().lstrip(".")
    if ext not in SOUNDFILE_EXPORTS:
        supported = ", ".join(f".{e}" for e in sorted(set(SOUNDFILE_EXPORTS)))
        raise ValueError(f"Unsupported format .{ext}. Supported: {supported}")
    file_fmt, subtype = SOUNDFILE_EXPORTS[ext]
    data = _to_mono_stereo(trimmed.astype(np.float32, copy=False))
    sf.write(path, data, sample_rate, format=file_fmt, subtype=subtype)