"""Blok fakta yang dikirim ke penulis narasi, dan daftar angka yang sah.

Tidak ada referensi lahan/komoditas/varietas di sini. Penyedia LLM pihak
ketiga tidak punya alasan melihat bahkan referensi buram sekalipun —
lihat tests/test_no_personal_data.py.
"""

from dataclasses import dataclass

from app.contracts.v1 import PlanResult
from app.problem import Problem

OBJECTIVE_LABEL = {
    "aman": "menjaga panen tidak menumpuk di satu minggu",
    "pendapatan": "mengejar nilai panen tertinggi",
    "pasar": "memenuhi permintaan pembeli yang sudah ada",
}


def format_number(value: float) -> str:
    """Cetak angka dengan gaya Indonesia: koma desimal, titik ribuan."""
    if abs(value - round(value)) < 0.005:
        return f"{round(value):,}".replace(",", ".")
    return f"{value:,.1f}".replace(",", "~").replace(".", ",").replace("~", ".")


def _variants(value: float) -> set[str]:
    """Setiap bentuk tercetak yang wajar untuk satu nilai terhitung yang sama."""
    forms = {format_number(value)}
    whole = round(value)
    if abs(value - whole) < 0.005:
        forms.add(str(whole))
    else:
        forms.add(f"{value:.1f}".replace(".", ","))
    return forms


@dataclass(frozen=True)
class Facts:
    """Angka yang sudah dihitung optimizer, siap dirangkai menjadi kalimat."""

    objective: str
    plots: int
    varieties: int
    first_harvest_week: str
    last_harvest_week: str
    harvest_weeks: int
    peak_p50: float
    peak_p90: float
    capacity: float | None
    total_tonnes: float
    demand_covered_kg: int
    seed: int

    @classmethod
    def from_plan(cls, plan: PlanResult, problem: Problem) -> "Facts":
        """Kumpulkan fakta sebuah rencana dari kandidat yang benar-benar dipilih."""
        chosen = problem.select(plan.candidate_ids)
        weeks = sorted({w for c in chosen for w in problem.weeks_of(c)})

        return cls(
            objective=plan.objective,
            plots=len({c.plot_ref for c in chosen}),
            varieties=len({c.variety_ref for c in chosen}),
            first_harvest_week=problem.weeks[weeks[0]] if weeks else "",
            last_harvest_week=problem.weeks[weeks[-1]] if weeks else "",
            harvest_weeks=len(weeks),
            peak_p50=plan.metrics.peak_tonnes_p50,
            peak_p90=plan.metrics.peak_tonnes_p90,
            capacity=problem.capacity,
            total_tonnes=round(plan.metrics.total_tonnes, 2),
            demand_covered_kg=plan.metrics.demand_covered_kg,
            seed=problem.seed,
        )

    def block(self) -> str:
        """Blok fakta apa adanya, satu-satunya sumber angka untuk narasi."""
        lines = [
            f"Tujuan rencana: {OBJECTIVE_LABEL[self.objective]}",
            f"Jumlah lahan yang ditanami: {format_number(self.plots)}",
            f"Jumlah varietas yang dipakai: {format_number(self.varieties)}",
            (
                f"Panen tersebar di {format_number(self.harvest_weeks)} minggu, "
                f"dari pekan {self.first_harvest_week} sampai pekan "
                f"{self.last_harvest_week}"
            ),
            f"Total panen musim ini: {format_number(self.total_tonnes)} ton",
            f"Puncak panen mingguan, perkiraan tengah: {format_number(self.peak_p50)} ton",
            (
                f"Puncak panen mingguan, sembilan dari sepuluh musim di bawah: "
                f"{format_number(self.peak_p90)} ton"
            ),
        ]
        if self.capacity is not None:
            lines.append(
                f"Kapasitas tampung per minggu: {format_number(self.capacity)} ton"
            )
        if self.demand_covered_kg:
            lines.append(
                f"Permintaan pembeli yang tertutup: "
                f"{format_number(self.demand_covered_kg)} kg"
            )
        return "\n".join(f"- {line}" for line in lines)

    def allowed_numbers(self) -> frozenset[str]:
        """Setiap angka yang boleh muncul di narasi, dalam bentuk tercetaknya."""
        allowed: set[str] = set()

        for value in (
            self.plots,
            self.varieties,
            self.harvest_weeks,
            self.total_tonnes,
            self.peak_p50,
            self.peak_p90,
            self.demand_covered_kg,
        ):
            allowed |= _variants(float(value))

        if self.capacity is not None:
            allowed |= _variants(self.capacity)

        for stamp in (self.first_harvest_week, self.last_harvest_week):
            for part in stamp.split("-"):
                if part:
                    allowed.add(part)
                    allowed.add(part.lstrip("0") or "0")

        return frozenset(allowed)
