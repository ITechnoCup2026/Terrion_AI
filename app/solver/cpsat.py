"""Solver eksak: satu model CP-SAT per objektif, deterministik dan berbatas waktu.

## Apa yang dimodelkan

Satu boolean per kandidat, tepat satu kandidat terpilih per lahan. Dari sana
tiga besaran yang sama dengan greedy dibangun sebagai ekspresi linear: puncak
mingguan, nilai kotor, dan kilogram permintaan yang tertutup.

## Dua tempat model ini SENGAJA berbeda dari greedy

Keduanya ditulis di sini supaya tidak ditemukan orang lain sebagai kejutan.

**1. Objektif "aman" dioptimalkan pada pengganti deterministik.** Greedy menilai
"aman" pada P90 Monte Carlo (`measure_for(score_on_p90=True)`). P90 adalah hasil
undian acak atas rencana yang dipilih — ia bukan fungsi linear dari variabel
keputusan, jadi tidak ada cara menuliskannya sebagai kendala.

Penggantinya adalah puncak mingguan kasus HARAPAN, dan pilihan itu diukur, bukan
ditebak. Pada berkas emas, diskor terhadap P90 yang sebenarnya:

    greedy                                 0,7305
    cp-sat, pengganti kasus terburuk       0,4077
    cp-sat, pengganti kasus harapan        0,8464

Pengganti kasus terburuk — seluruh batas atas menumpuk di titik tengah jendela —
tampak masuk akal tetapi jauh lebih buruk: menekan puncak yang dikuncupkan itu
mendorong rencana ke bentuk yang tidak ada hubungannya dengan sebaran yang
diundi Monte Carlo. Sebaran mingguan kasus harapan justru menangkapnya.

Walau begitu "aman" TIDAK PERNAH melaporkan OPTIMAL: yang terbukti optimal
adalah penggantinya, bukan P90 yang dibaca pengurus.

**2. Normalisasi tidak dijepit.** `scalarise` menjepit tiap besaran ke 0..1
terhadap rentang yang dicapai tiga greedy satu kriteria. Penjepitan itu artefak
dari cara rentangnya diperoleh, bukan maksud produknya: kalau solver eksak
menemukan pendapatan di atas rentang yang sempat dicapai greedy, menjepitnya
berarti membuang temuan yang lebih baik. Karena konstanta lo/hi hilang di dalam
argmax, tujuannya menjadi linear murni terhadap ketiga besaran.
"""

from app.config import settings
from app.contracts.v1 import Candidate
from app.problem import Problem
from app.solver.errors import SolverFailed
from app.solver.metrics import KG_PER_TONNE
from app.solver.objectives import USES_WORST_CASE, WEIGHTS, Bounds, Weights

# Tonase disimpan sebagai kilogram bulat. Sebaran mingguan adalah pecahan
# (tonase dibagi jumlah minggu), jadi presisi kilogram sudah lebih dari cukup
# dan ia menjauhkan seluruh model dari bilangan pecahan.
KG = KG_PER_TONNE

# Sasaran besaran suku tujuan terbesar setelah diskalakan ke bilangan bulat.
# Cukup besar untuk menjaga presisi koefisien terkecil, cukup kecil supaya
# jumlah ketiga suku tetap jauh di dalam int64.
OBJECTIVE_MAGNITUDE = 10**15


def solver_available() -> bool:
    """Apakah CP-SAT bisa dimuat di lingkungan ini."""
    try:
        from ortools.sat.python import cp_model  # noqa: F401
    except ImportError:
        return False
    return True


def _week_kg(problem: Problem, candidate: Candidate, worst: bool) -> dict[int, int]:
    """Sebaran tonase kandidat ke minggu, dalam kilogram bulat."""
    return {
        week: round(tonnes * KG)
        for week, tonnes in problem.week_share(candidate, worst).items()
    }


def _income(candidate: Candidate) -> int:
    """Nilai kotor kandidat dalam rupiah bulat; nol bila harganya belum ada.

    Sama dengan `measure`: kandidat tanpa harga acuan menyumbang nol pada
    pendapatan. Yang membedakan "nol" dari "belum ada angkanya" adalah
    `gross_value`, dan itu dilaporkan terpisah, bukan dioptimalkan.
    """
    if candidate.price_per_kg is None:
        return 0
    return round(candidate.tonnes_mid * KG * candidate.price_per_kg)


def _coefficients(
    objective: str,
    bounds: Bounds,
    magnitudes: tuple[int, int, int],
    weights: Weights | None = None,
) -> tuple[int, int, int]:
    """Koefisien bulat untuk (puncak, pendapatan, cakupan).

    Konstanta lo/hi pada normalisasi hilang di dalam argmax, jadi yang tersisa
    hanyalah bobot dibagi lebar rentangnya. Dua hal yang mudah salah di sini,
    dan keduanya pernah salah:

    **Satuan.** `bounds` menyimpan puncak dalam TON, sementara variabel model
    dalam KILOGRAM. Tanpa pembagian dengan KG, suku puncak menjadi seribu kali
    terlalu kuat dan solver berhenti peduli pada pendapatan sama sekali.

    **Pembulatan.** Rupiah berukuran miliaran sementara kilogram berukuran
    ribuan, jadi kemiringan pendapatan beberapa orde lebih kecil daripada
    kemiringan puncak. Menskalakan terhadap kemiringan terbesar membulatkan
    koefisien pendapatan menjadi NOL. Karena itu penskalaannya memakai
    sumbangan terbesar tiap suku — kemiringan dikali jangkauan variabelnya —
    yang besarnya sebanding antar suku menurut konstruksi.

    Rentang puncak selalu diambil dari kasus harapan, sepadan dengan besaran
    yang benar-benar dimodelkan — termasuk untuk "aman", yang DISKOR pada P90
    tetapi DIMODELKAN pada kasus harapan.
    """
    w_peak, w_income, w_market = (weights or WEIGHTS)[objective]

    def slope(weight: float, span: tuple[float, float]) -> float:
        low, high = span
        return 0.0 if high - low < 1e-9 else weight / (high - low)

    raw = (
        -slope(w_peak, bounds.peak_expected) / KG,
        slope(w_income, bounds.income),
        slope(w_market, bounds.coverage),
    )

    largest = max(abs(value) * span for value, span in zip(raw, magnitudes))
    if largest < 1e-15:
        raise SolverFailed("tidak ada besaran yang membedakan rencana")

    factor = OBJECTIVE_MAGNITUDE / largest
    return tuple(round(value * factor) for value in raw)


def solve(
    problem: Problem,
    objective: str,
    bounds: Bounds,
    seed: int,
    weights: Weights | None = None,
) -> tuple[list[str], str, int]:
    """Selesaikan satu objektif; kembalikan id terpilih, status, dan cabang."""
    from ortools.sat.python import cp_model

    model = cp_model.CpModel()

    taken = {c.id: model.NewBoolVar("x_" + c.id) for c in problem.by_id.values()}

    # Tepat satu kandidat per lahan, sama seperti greedy: ia selalu memilih satu
    # opsi untuk setiap lahan yang punya opsi.
    for plot_ref in problem.plot_refs:
        model.AddExactlyOne(taken[c.id] for c in problem.by_plot[plot_ref])

    # Puncak mingguan. Karena bobot puncak selalu positif, tujuan yang menekannya
    # ke bawah membuat variabel ini duduk tepat di beban minggu tertinggi — tidak
    # perlu kesamaan maksimum yang jauh lebih mahal.
    total_kg = sum(round(c.tonnes_high * KG) for c in problem.by_id.values())
    peak = model.NewIntVar(0, max(total_kg, 1), "peak_kg")
    # Sebaran kasus harapan untuk SEMUA objektif — lihat docstring modul: ia
    # pengganti P90 yang jauh lebih baik daripada puncak yang dikuncupkan.
    load: list[list[tuple[object, int]]] = [[] for _ in problem.weeks]
    for candidate in problem.by_id.values():
        for week, kg in _week_kg(problem, candidate, worst=False).items():
            load[week].append((taken[candidate.id], kg))
    for terms in load:
        if terms:
            model.Add(peak >= sum(var * kg for var, kg in terms))

    income = sum(taken[c.id] * _income(c) for c in problem.by_id.values())

    # Cakupan permintaan: pasokan yang melebihi permintaan satu minggu tidak
    # dihitung. Batas atasnya permintaan itu sendiri, dan karena bobot pasar
    # selalu positif, variabelnya terdorong naik sampai menyentuh pasokan.
    supply: dict[tuple[str, int], list[tuple[object, int]]] = {}
    for candidate in problem.by_id.values():
        for week, kg in _week_kg(problem, candidate, worst=False).items():
            supply.setdefault((candidate.commodity_ref, week), []).append(
                (taken[candidate.id], kg)
            )

    covered = []
    for slot, wanted_kg in problem.demand_kg.items():
        terms = supply.get(slot)
        if not terms:
            continue
        slot_cover = model.NewIntVar(0, int(wanted_kg), f"cover_{slot[0]}_{slot[1]}")
        model.Add(slot_cover <= sum(var * kg for var, kg in terms))
        covered.append(slot_cover)

    coverage = sum(covered) if covered else 0

    # Jangkauan tiap variabel: dipakai menyetarakan suku tujuan yang satuannya
    # berbeda jauh. Pendapatan diambil per lahan karena hanya satu kandidat per
    # lahan yang bisa terpilih.
    top_income = sum(
        max((_income(c) for c in problem.by_plot[plot_ref]), default=0)
        for plot_ref in problem.plot_refs
    )
    magnitudes = (
        max(total_kg, 1),
        max(top_income, 1),
        max(int(sum(problem.demand_kg.values())), 1),
    )

    peak_coef, income_coef, coverage_coef = _coefficients(
        objective, bounds, magnitudes, weights
    )
    model.Maximize(peak_coef * peak + income_coef * income + coverage_coef * coverage)

    solver = cp_model.CpSolver()
    # Satu pekerja dan benih tetap: pencarian paralel CP-SAT tidak deterministik,
    # dan demo yang angkanya berubah tiap dijalankan tidak bisa dipercaya.
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = seed
    # Anggaran dibagi rata antar objektif, bukan diberikan penuh kepada
    # masing-masing: sisi Go menutup seluruh panggilan pada 3,5 detik, dan
    # narasi masih perlu bagiannya sesudah ini.
    solver.parameters.max_time_in_seconds = max(
        0.05, settings.solver_time_limit_ms / 1000 / max(len(problem.objectives), 1)
    )

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverFailed("CP-SAT tidak menemukan solusi: " + solver.StatusName(status))

    chosen = [c.id for c in problem.by_id.values() if solver.Value(taken[c.id])]

    return chosen, _status_name(status, objective, cp_model), solver.NumBranches()


def _status_name(status, objective: str, cp_model) -> str:
    """Status yang tidak mengklaim lebih dari yang dibuktikan.

    "aman" dioptimalkan pada pengganti deterministik, bukan pada P90 yang
    dilaporkan, jadi optimalitas yang dibuktikan CP-SAT bukan optimalitas angka
    yang dibaca pengurus. Ia dilaporkan FEASIBLE.
    """
    if status == cp_model.OPTIMAL and not USES_WORST_CASE[objective]:
        return "OPTIMAL"
    return "FEASIBLE"
