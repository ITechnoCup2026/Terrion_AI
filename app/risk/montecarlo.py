"""Propagasi ketidakpastian: kuantil puncak tonase mingguan.

Solver memakai satu angka per kandidat. Kontrak memberi tiga, ditambah sebuah
jendela panen. Selisih itu adalah risikonya, dan di sinilah ia dihitung.
"""

import numpy as np

from app.contracts.v1 import Candidate
from app.problem import Problem


def triangular_icdf(
    u: np.ndarray, low: np.ndarray, mid: np.ndarray, high: np.ndarray
) -> np.ndarray:
    """Ubah undian seragam menjadi undian distribusi segitiga.

    Segitiga adalah distribusi kanonik untuk estimasi tiga titik: ia tidak
    menuntut satu pun asumsi di luar tiga angka yang sudah kita punya.
    """
    span = np.where(high > low, high - low, 1e-9)
    pivot = (mid - low) / span
    left = low + np.sqrt(u * span * (mid - low))
    right = high - np.sqrt((1.0 - u) * span * (high - mid))
    return np.where(u < pivot, left, right)


def peak_quantiles(
    chosen: tuple[Candidate, ...], problem: Problem, draws: int, seed: int
) -> tuple[float, float]:
    """Puncak mingguan pada persentil 50 dan 90 atas ribuan musim simulasi."""
    if not chosen or draws <= 0:
        return 0.0, 0.0

    rng = np.random.default_rng(seed)
    spans = [problem.span[c.id] for c in chosen]

    starts = np.array([s for s, _ in spans])
    ends = np.array([e for _, e in spans])
    low = np.array([c.tonnes_low for c in chosen])
    mid = np.array([c.tonnes_mid for c in chosen])
    high = np.array([c.tonnes_high for c in chosen])

    week = rng.integers(starts, ends + 1, size=(draws, len(chosen)))
    tonnes = triangular_icdf(rng.random((draws, len(chosen))), low, mid, high)

    totals = np.zeros((draws, len(problem.weeks)))
    np.add.at(totals, (np.arange(draws)[:, None], week), tonnes)

    peak = totals.max(axis=1)
    return round(float(np.percentile(peak, 50)), 2), round(float(np.percentile(peak, 90)), 2)
