"""Solver eksak: apa yang ia janjikan, dan apa yang sengaja tidak ia janjikan."""

import pytest

from app.solver import cpsat_available, derive_bounds, solve_all
from app.solver.greedy import solve as greedy_solve
from app.solver.metrics import measure_for
from app.solver.objectives import USES_WORST_CASE, scalarise

cpsat = pytest.importorskip("app.solver.cpsat")

pytestmark = pytest.mark.skipif(
    not cpsat_available(), reason="ortools tidak terpasang di lingkungan ini"
)


def test_cpsat_is_the_engine_when_ortools_is_installed(problem):
    _, solver, _, _ = solve_all(problem, problem.seed)

    assert solver == "cp-sat", (
        "ortools terpasang tetapi jalur yang terpakai bukan CP-SAT — "
        "layanan diam-diam turun ke solver cadangan"
    )


def test_every_plot_gets_exactly_one_candidate(problem):
    solutions, _, _, _ = solve_all(problem, problem.seed)

    for objective, ids in solutions.items():
        chosen = problem.select(ids)
        plots = [c.plot_ref for c in chosen]

        assert len(plots) == len(set(plots)), (
            f"objektif {objective} menanami satu lahan dua kali"
        )
        assert set(plots) == set(problem.plot_refs), (
            f"objektif {objective} meninggalkan lahan tanpa penugasan"
        )


def test_the_same_problem_and_seed_give_the_same_plan(problem):
    first, _, _, _ = solve_all(problem, problem.seed)
    second, _, _, _ = solve_all(problem, problem.seed)

    assert first == second, (
        "CP-SAT mengembalikan rencana berbeda untuk masalah dan benih yang sama; "
        "demo yang angkanya berubah tiap dijalankan tidak bisa dipercaya"
    )


@pytest.mark.parametrize("objective", ["pendapatan", "pasar"])
def test_cpsat_is_never_worse_than_greedy_where_the_model_is_exact(problem, objective):
    """Inilah alasan solver eksak ada.

    Untuk kedua objektif ini besaran yang dinilai deterministik, jadi model
    CP-SAT menyatakan tujuan yang sama persis dengan yang diskor greedy — dan
    solver eksak tidak boleh kalah oleh heuristik pada tujuannya sendiri.
    """
    bounds = derive_bounds(problem)

    exact_ids, _, _ = cpsat.solve(problem, objective, bounds, problem.seed)
    heuristic_ids, _ = greedy_solve(problem, objective, bounds)

    def score(ids: list[str]) -> float:
        chosen = problem.select(ids)
        return scalarise(
            measure_for(chosen, problem, USES_WORST_CASE[objective]), objective, bounds
        )

    assert score(exact_ids) >= score(heuristic_ids) - 1e-9, (
        f"CP-SAT kalah dari greedy pada objektif {objective}: "
        f"{score(exact_ids):.6f} < {score(heuristic_ids):.6f}"
    )


def test_safe_never_claims_optimal_because_it_optimises_a_stand_in(problem):
    """Objektif "aman" diskor pada P90 Monte Carlo, yang tidak bisa dimodelkan.

    CP-SAT boleh membuktikan optimalitas penggantinya yang deterministik, tetapi
    yang dibaca pengurus adalah P90 — jadi status yang dilaporkan tidak boleh
    mengklaim optimalitas atas angka itu.
    """
    bounds = derive_bounds(problem)
    _, status, _ = cpsat.solve(problem, "aman", bounds, problem.seed)

    assert status == "FEASIBLE", (
        f"status {status!r} mengklaim lebih dari yang dibuktikan: yang optimal "
        f"adalah pengganti deterministiknya, bukan P90 yang dilaporkan"
    )


def test_a_missing_ortools_falls_back_instead_of_failing(problem, monkeypatch):
    """Layanan tanpa ortools harus tetap menjawab dengan angka yang benar."""
    import builtins

    real_import = builtins.__import__

    def refuse_ortools(name, *args, **kwargs):
        if name.startswith("ortools"):
            raise ImportError("ortools sengaja disembunyikan")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", refuse_ortools)

    solutions, solver, status, _ = solve_all(problem, problem.seed)

    assert solver == "greedy"
    assert status == "HEURISTIC"
    assert all(solutions[o] for o in problem.objectives)


def test_shifted_weights_actually_reach_the_solver(problem):
    """Lapis tujuan hanya berguna kalau bobotnya benar-benar mengubah rencana.

    Pergeseran yang dihasilkan model biasanya kecil (0,70 menjadi 0,75) dan
    sering tidak menggeser argmax sama sekali — itu wajar. Yang tidak boleh
    terjadi adalah bobot diterima, dicatat, lalu diam-diam tidak terpakai.
    """
    ekstrem = {
        "aman": (0.95, 0.03, 0.02),
        "pendapatan": (0.02, 0.96, 0.02),
        "pasar": (0.02, 0.03, 0.95),
    }

    bawaan, _, _, _ = solve_all(problem, problem.seed)
    digeser, _, _, _ = solve_all(problem, problem.seed, ekstrem)

    assert bawaan != digeser, (
        "bobot yang digeser jauh menghasilkan rencana yang sama persis; "
        "lapis tujuan tidak menyentuh solver"
    )
