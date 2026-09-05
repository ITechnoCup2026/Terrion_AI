"""Pengukuran sebuah rencana: puncak mingguan, nilai kotor, cakupan permintaan."""

from dataclasses import dataclass, replace

from app.contracts.v1 import Candidate
from app.problem import Problem
from app.risk.montecarlo import peak_quantiles

KG_PER_TONNE = 1000.0

# Undian yang dipakai di dalam gelung pencarian. Angka penuh (2000) dipakai
# hanya untuk metrik yang dilaporkan; 256 sudah cukup untuk mengurutkan opsi.
SEARCH_DRAWS = 256


@dataclass(frozen=True)
class Measures:
    """Tiga besaran yang dinilai, ditambah dua yang hanya dilaporkan."""

    peak: float
    income: float
    coverage_kg: int
    total_tonnes: float
    gross_value: float | None


def weekly_totals(chosen: tuple[Candidate, ...], problem: Problem, worst: bool) -> list[float]:
    """Tonase yang tiba tiap minggu bila rencana ini dijalankan."""
    totals = [0.0] * len(problem.weeks)
    for candidate in chosen:
        for week, tonnes in problem.week_share(candidate, worst).items():
            totals[week] += tonnes
    return totals


def demand_covered(chosen: tuple[Candidate, ...], problem: Problem) -> int:
    """Kilogram permintaan pembeli yang benar-benar tertutup rencana ini.

    Pasokan yang melebihi permintaan satu minggu tidak dihitung — menanam dua
    kali lipat dari yang diminta bukan berarti melayani dua kali lipat.
    """
    supply: dict[tuple[str, int], float] = {}
    for candidate in chosen:
        for week, tonnes in problem.week_share(candidate, worst=False).items():
            slot = (candidate.commodity_ref, week)
            supply[slot] = supply.get(slot, 0.0) + tonnes * KG_PER_TONNE

    return int(sum(min(kg, supply.get(slot, 0.0)) for slot, kg in problem.demand_kg.items()))


def measure(chosen: tuple[Candidate, ...], problem: Problem, worst: bool) -> Measures:
    """Ukur satu rencana lengkap."""
    if not chosen:
        return Measures(peak=0.0, income=0.0, coverage_kg=0, total_tonnes=0.0, gross_value=0.0)

    peak = max(weekly_totals(chosen, problem, worst), default=0.0)
    total_tonnes = sum(c.tonnes_mid for c in chosen)

    priced = [c for c in chosen if c.price_per_kg is not None]
    income = sum(c.tonnes_mid * KG_PER_TONNE * (c.price_per_kg or 0.0) for c in priced)
    gross_value = income if len(priced) == len(chosen) else None

    return Measures(
        peak=peak,
        income=income,
        coverage_kg=demand_covered(chosen, problem),
        total_tonnes=total_tonnes,
        gross_value=gross_value,
    )


def measure_for(
    chosen: tuple[Candidate, ...],
    problem: Problem,
    score_on_p90: bool,
    draws: int = SEARCH_DRAWS,
) -> Measures:
    """Ukur rencana, dengan puncak diambil dari P90 bila objektifnya menuntutnya.

    Objektif "aman" dinilai pada angka yang juga dilaporkan ke pengguna. Kalau
    ia dinilai pada proksi lain, rencana "aman" bisa keluar dengan P90 lebih
    buruk daripada rencana lain, dan label di layar berhenti berarti.
    """
    reported = measure(chosen, problem, worst=False)
    if not score_on_p90 or not chosen:
        return reported
    _, p90 = peak_quantiles(chosen, problem, draws, problem.seed)
    return replace(reported, peak=p90)


def plan_result(
    objective: str,
    chosen: tuple[Candidate, ...],
    problem: Problem,
    peak_p50: float,
    peak_p90: float,
):
    """Rakit satu entri rencana untuk respons, dengan narasi menyusul kemudian."""
    from app.contracts.v1 import Metrics, PlanResult

    reported = measure(chosen, problem, worst=False)
    return PlanResult(
        objective=objective,
        candidate_ids=[c.id for c in chosen],
        metrics=Metrics(
            peak_tonnes_p50=peak_p50,
            peak_tonnes_p90=peak_p90,
            total_tonnes=round(reported.total_tonnes, 2),
            gross_value=reported.gross_value,
            demand_covered_kg=reported.coverage_kg,
        ),
        narrative=None,
        narrative_source="none",
    )
