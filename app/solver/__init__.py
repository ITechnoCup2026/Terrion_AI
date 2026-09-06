"""Pemilihan mesin solver dan penurunan batas normalisasi."""

from app.problem import Problem
from app.solver.errors import SolverFailed
from app.solver.greedy import probe
from app.solver.greedy import solve as greedy_solve
from app.solver.objectives import Bounds, Weights

__all__ = [
    "Bounds",
    "SolverFailed",
    "cpsat_available",
    "derive_bounds",
    "solve_all",
    "warm_solver",
]


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


def warm_solver() -> None:
    """Muat CP-SAT sebelum permintaan pertama tiba.

    Mengimpor ortools memakan 549 ms sekali per proses; sesudah itu satu
    penyelesaian penuh hanya 45 ms. Dibayar di dalam permintaan pertama, angka
    itu setara dengan seluruh anggaran solver, dan bentuk kegagalannya persis
    sama dengan handshake TLS yang sudah kita pindahkan ke startup: permintaan
    pertama setelah deploy jauh lebih lambat, sisanya baik-baik saja.

    Tidak adanya ortools bukan galat — layanan memang boleh berjalan dengan
    solver cadangan.
    """
    try:
        from ortools.sat.python import cp_model  # noqa: F401
    except ImportError:
        return


def cpsat_available() -> bool:
    """Apakah solver CP-SAT bisa dimuat di lingkungan ini."""
    try:
        from app.solver.cpsat import solver_available
    except ImportError:
        return False
    return solver_available()


def solve_all(
    problem: Problem, seed: int, weights: Weights | None = None
) -> tuple[dict[str, list[str]], str, str, int]:
    """Selesaikan setiap objektif yang diminta, dengan greedy sebagai cadangan.

    `weights` yang bukan None berasal dari lapis tujuan: kalimat pengurus yang
    sudah diterjemahkan menjadi bobot. Ia hanya menggeser bobot; setiap angka
    yang keluar tetap dihitung solver deterministik di bawah ini.
    """
    bounds = derive_bounds(problem)

    try:
        return _with_cpsat(problem, bounds, seed, weights)
    except (ImportError, SolverFailed):
        return _with_greedy(problem, bounds, weights)


def _with_cpsat(
    problem: Problem, bounds: Bounds, seed: int, weights: Weights | None = None
) -> tuple[dict[str, list[str]], str, str, int]:
    """Jalur utama: CP-SAT, tetapi greedy tetap ikut dan yang terbaik yang menang.

    Kenapa portofolio dan bukan CP-SAT sendirian. Untuk "pendapatan" dan "pasar"
    model CP-SAT menyatakan tujuan yang sama persis dengan yang diskor, jadi ia
    membuktikan optimalitas dan greedy tidak pernah mengunggulinya. Untuk "aman"
    tidak begitu: yang diskor adalah P90 Monte Carlo, yang tidak bisa dimodelkan,
    sehingga CP-SAT mengoptimalkan pengganti deterministik. Diukur pada berkas
    emas, pengganti itu justru menghasilkan rencana yang LEBIH BURUK pada P90
    (0,41 berbanding 0,73) — dan "aman" yang puncaknya lebih tinggi adalah
    kegagalan produk, bukan sekadar angka yang kurang rapi.

    Jadi keduanya dijalankan dan pemenangnya dipilih menurut skor yang sama
    dengan yang dibaca pengguna. Greedy hanya memakan 1-10 ms, jadi jaminan
    "tidak pernah lebih buruk dari sebelumnya" ini praktis gratis.
    """
    from app.solver.cpsat import solve as cpsat_solve

    solutions: dict[str, list[str]] = {}
    statuses: list[str] = []
    evaluations = 0

    for objective in problem.objectives:
        exact_ids, status, branches = cpsat_solve(
            problem, objective, bounds, seed, weights
        )
        heuristic_ids, used = greedy_solve(problem, objective, bounds, weights)
        evaluations += branches + used

        if _score(heuristic_ids, problem, objective, bounds, weights) > _score(
            exact_ids, problem, objective, bounds, weights
        ):
            solutions[objective] = heuristic_ids
            statuses.append("HEURISTIC")
        else:
            solutions[objective] = exact_ids
            statuses.append(status)

    status = "OPTIMAL" if all(s == "OPTIMAL" for s in statuses) else "FEASIBLE"
    return solutions, "cp-sat", status, evaluations


def _score(
    ids: list[str],
    problem: Problem,
    objective: str,
    bounds: Bounds,
    weights: Weights | None = None,
) -> float:
    """Skor sebuah rencana pada tujuan yang sama dengan yang dilaporkan."""
    from app.solver.metrics import measure_for
    from app.solver.objectives import USES_WORST_CASE, scalarise

    chosen = problem.select(ids)
    return scalarise(
        measure_for(chosen, problem, USES_WORST_CASE[objective]), objective, bounds, weights
    )


def _with_greedy(
    problem: Problem, bounds: Bounds, weights: Weights | None = None
) -> tuple[dict[str, list[str]], str, str, int]:
    """Jalur cadangan — selalu tersedia, tanpa dependensi biner apa pun."""
    solutions: dict[str, list[str]] = {}
    evaluations = 0

    for objective in problem.objectives:
        ids, count = greedy_solve(problem, objective, bounds, weights)
        solutions[objective] = ids
        evaluations += count

    return solutions, "greedy", "HEURISTIC", evaluations
