"""Tiga objektif, bobotnya, dan cara tiga besaran dijadikan satu skor."""

from dataclasses import dataclass

from app.solver.metrics import Measures

# Urutan bobot: (ratakan puncak, maksimalkan pendapatan, penuhi permintaan).
WEIGHTS: dict[str, tuple[float, float, float]] = {
    "aman": (0.70, 0.20, 0.10),
    "pendapatan": (0.15, 0.75, 0.10),
    "pasar": (0.20, 0.20, 0.60),
}

# "Aman" diskor pada puncak kasus terburuk. Itu definisi kata itu, bukan detail.
USES_WORST_CASE: dict[str, bool] = {"aman": True, "pendapatan": False, "pasar": False}

CRITERIA = ("peak", "income", "coverage")


@dataclass(frozen=True)
class Bounds:
    """Rentang yang benar-benar dicapai untuk tiap besaran, dipakai menormalkan.

    Puncak punya dua rentang karena ia diukur dengan dua cara. Menormalkan
    puncak kasus terburuk terhadap rentang kasus harapan akan menjepit setiap
    opsi ke nilai yang sama, dan bobot puncak berhenti bekerja tanpa suara.
    """

    peak_expected: tuple[float, float]
    peak_worst: tuple[float, float]
    income: tuple[float, float]
    coverage: tuple[float, float]

    def peak_span(self, objective: str) -> tuple[float, float]:
        """Rentang puncak yang sepadan dengan cara objektif ini diskor."""
        return self.peak_worst if USES_WORST_CASE[objective] else self.peak_expected


def normalise(value: float, span: tuple[float, float]) -> float:
    """Petakan sebuah nilai ke 0..1 terhadap rentang yang tercapai."""
    low, high = span
    if high - low < 1e-9:
        return 0.0
    return min(1.0, max(0.0, (value - low) / (high - low)))


def criterion_value(measures: Measures, criterion: str) -> float:
    """Ambil satu besaran mentah, dengan puncak dibalik agar besar selalu baik."""
    if criterion == "peak":
        return -measures.peak
    if criterion == "income":
        return measures.income
    return float(measures.coverage_kg)


def scalarise(measures: Measures, objective: str, bounds: Bounds) -> float:
    """Gabungkan tiga besaran menjadi satu skor, makin besar makin baik."""
    w_peak, w_income, w_market = WEIGHTS[objective]
    return (
        w_peak * (1.0 - normalise(measures.peak, bounds.peak_span(objective)))
        + w_income * normalise(measures.income, bounds.income)
        + w_market * normalise(float(measures.coverage_kg), bounds.coverage)
    )
