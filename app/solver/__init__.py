"""Pemilihan mesin solver dan penurunan batas normalisasi."""

from app.problem import Problem
from app.solver.errors import SolverFailed
from app.solver.greedy import probe
from app.solver.greedy import solve as greedy_solve
from app.solver.objectives import Bounds

__all__ = ["Bounds", "SolverFailed", "cpsat_available", "derive_bounds", "solve_all"]


def derive_bounds(problem: Problem) -> Bounds:
    """Cari rentang yang benar-benar tercapai dengan tiga greedy satu kriteria.

    Batas teoretis (nol sampai seluruh tonase) akan membuat setiap skor
    menempel di ujung yang sama dan bobot kehilangan artinya.
    """
    criteria = ("peak", "income", "coverage")
    expected = [probe(problem, criterion, score_on_p90=False) for criterion in criteria]
    worst = [probe(problem, criterion, score_on_p90=True) for criterion in criteria]

    incomes = [m.income for m in expected]
    coverages = [float(m.coverage_kg) for m in expected]

    return Bounds(
        peak_expected=(min(m.peak for m in expected), max(m.peak for m in expected)),
        peak_worst=(min(m.peak for m in worst), max(m.peak for m in worst)),
        income=(min(incomes), max(incomes)),
        coverage=(min(coverages), max(coverages)),
    )


def cpsat_available() -> bool:
    """Apakah solver CP-SAT bisa dimuat di lingkungan ini."""
    try:
        from app.solver.cpsat import solver_available
    except ImportError:
        return False
    return solver_available()


def solve_all(
    problem: Problem, seed: int
) -> tuple[dict[str, list[str]], str, str, int]:
    """Selesaikan setiap objektif yang diminta, dengan greedy sebagai cadangan."""
    bounds = derive_bounds(problem)

    try:
        return _with_cpsat(problem, bounds, seed)
    except (ImportError, SolverFailed):
        return _with_greedy(problem, bounds)


def _with_cpsat(
    problem: Problem, bounds: Bounds, seed: int
) -> tuple[dict[str, list[str]], str, str, int]:
    """Jalur utama — tersedia mulai Fase 2, ketika app/solver/cpsat.py ada."""
    from app.solver.cpsat import solve as cpsat_solve

    solutions: dict[str, list[str]] = {}
    statuses: list[str] = []
    evaluations = 0

    for objective in problem.objectives:
        ids, status, branches = cpsat_solve(problem, objective, bounds, seed)
        solutions[objective] = ids
        statuses.append(status)
        evaluations += branches

    status = "OPTIMAL" if all(s == "OPTIMAL" for s in statuses) else "FEASIBLE"
    return solutions, "cp-sat", status, evaluations


def _with_greedy(
    problem: Problem, bounds: Bounds
) -> tuple[dict[str, list[str]], str, str, int]:
    """Jalur cadangan — selalu tersedia, tanpa dependensi biner apa pun."""
    solutions: dict[str, list[str]] = {}
    evaluations = 0

    for objective in problem.objectives:
        ids, count = greedy_solve(problem, objective, bounds)
        solutions[objective] = ids
        evaluations += count

    return solutions, "greedy", "HEURISTIC", evaluations
