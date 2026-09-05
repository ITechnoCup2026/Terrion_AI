"""Solver cadangan: greedy per lahan, lalu perbaikan lokal dengan penukaran.

Cermin dari planning.Search di sisi Go. Kesamaannya disengaja — itu yang
membuat kedua mesin bisa dibandingkan di harness evaluasi.
"""

from app.contracts.v1 import Candidate
from app.problem import Problem
from app.solver.metrics import Measures, measure_for
from app.solver.objectives import USES_WORST_CASE, Bounds, criterion_value, scalarise

TOLERANCE = 1e-12
IMPROVE_PASSES = 3


def _score(
    chosen: list[Candidate], problem: Problem, objective: str, bounds: Bounds
) -> float:
    """Skor terskalarisasi sebuah rencana untuk satu objektif."""
    return scalarise(
        measure_for(tuple(chosen), problem, USES_WORST_CASE[objective]), objective, bounds
    )


def probe(problem: Problem, criterion: str, score_on_p90: bool = False) -> Measures:
    """Greedy satu kriteria, dipakai hanya untuk menemukan rentang yang tercapai."""
    chosen: list[Candidate] = []
    for plot_ref in problem.plot_refs:
        best, best_value = None, float("-inf")
        for candidate in problem.by_plot[plot_ref]:
            value = criterion_value(
                measure_for(tuple(chosen + [candidate]), problem, score_on_p90), criterion
            )
            if value > best_value + TOLERANCE:
                best, best_value = candidate, value
        if best is not None:
            chosen.append(best)
    return measure_for(tuple(chosen), problem, score_on_p90)


def greedy(
    problem: Problem, objective: str, bounds: Bounds
) -> tuple[list[Candidate], int]:
    """Pilih satu kandidat terbaik per lahan, menurut urutan lahan yang tetap."""
    chosen: list[Candidate] = []
    evaluations = 0

    for plot_ref in problem.plot_refs:
        best, best_score = None, float("-inf")
        for candidate in problem.by_plot[plot_ref]:
            score = _score(chosen + [candidate], problem, objective, bounds)
            evaluations += 1
            if score > best_score + TOLERANCE:
                best, best_score = candidate, score
        if best is not None:
            chosen.append(best)

    return chosen, evaluations


def improve(
    problem: Problem,
    objective: str,
    bounds: Bounds,
    chosen: list[Candidate],
    passes: int = IMPROVE_PASSES,
) -> tuple[list[Candidate], int]:
    """Tukar satu pilihan pada satu lahan selama penukaran itu menaikkan skor."""
    evaluations = 0
    current_score = _score(chosen, problem, objective, bounds)

    for _ in range(passes):
        moved = False
        for position, current in enumerate(chosen):
            for alternative in problem.by_plot[current.plot_ref]:
                if alternative.id == current.id:
                    continue
                trial = list(chosen)
                trial[position] = alternative
                trial_score = _score(trial, problem, objective, bounds)
                evaluations += 1
                if trial_score > current_score + TOLERANCE:
                    chosen, current_score, moved = trial, trial_score, True
        if not moved:
            break

    return chosen, evaluations


def solve(
    problem: Problem, objective: str, bounds: Bounds
) -> tuple[list[str], int]:
    """Greedy lalu perbaikan lokal; kembalikan id terpilih dan jumlah evaluasi."""
    chosen, first = greedy(problem, objective, bounds)
    chosen, second = improve(problem, objective, bounds, chosen)
    return [c.id for c in chosen], first + second
