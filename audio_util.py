"""Level helpers."""
from __future__ import annotations

import numpy as np


def peak_dbfs(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    peak = float(np.max(np.abs(samples)))
    if peak < 1e-9:
        return -120.0
    return 20.0 * np.log10(peak)


def apply_gain_db(samples: np.ndarray, gain_db: float) -> np.ndarray:
    if samples.size == 0 or gain_db == 0.0:
        return samples
    out = samples.astype(np.float32, copy=True)
    out *= 10.0 ** (gain_db / 20.0)
    return np.clip(out, -1.0, 1.0)


def downmix_stereo(samples: np.ndarray) -> np.ndarray:
    if samples.ndim == 1:
        return samples.reshape(-1, 1)
    if samples.shape[1] == 1:
        return samples
    if samples.shape[1] == 2:
        return samples
    left = samples[:, 0]
    right = samples[:, 1] if samples.shape[1] > 1 else samples[:, 0]
    return np.column_stack([left, right]).astype(np.float32, copy=False)