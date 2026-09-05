"""Bentuk internal soal perencanaan, diturunkan sekali dari kontrak.

Seluruh aritmetika tanggal terjadi di berkas ini dan tidak di tempat lain.
Setelah melewati Problem.from_request, sebuah minggu adalah indeks bilangan
bulat dan bukan lagi sebuah tanggal.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.contracts.v1 import Candidate, ProposeRequest


def parse_date(iso: str) -> date:
    """Baca tanggal YYYY-MM-DD tanpa zona waktu."""
    return date.fromisoformat(iso)


def week_start(day: date) -> date:
    """Senin dari minggu yang memuat hari ini — kunci minggu di seluruh sistem."""
    return day - timedelta(days=day.weekday())


def week_key(day: date) -> str:
    """Kunci minggu dalam bentuk tercetaknya, mis. '2027-01-04'."""
    return week_start(day).isoformat()


@dataclass(frozen=True)
class Problem:
    """Soal yang sudah siap dioptimasi: minggu terurut, kandidat terkelompok."""

    weeks: tuple[str, ...]
    week_index: dict[str, int]
    candidates: tuple[Candidate, ...]
    by_id: dict[str, Candidate]
    by_plot: dict[str, tuple[Candidate, ...]]
    plot_refs: tuple[str, ...]
    span: dict[str, tuple[int, int]]
    demand_kg: dict[tuple[str, int], int]
    capacity: float | None
    objectives: tuple[str, ...]
    seed: int

    @classmethod
    def from_request(cls, payload: ProposeRequest) -> "Problem":
        """Terjemahkan permintaan menjadi bentuk internal yang terurut penuh."""
        candidates = tuple(sorted(payload.candidates, key=lambda c: c.id))

        keys: set[str] = set()
        for candidate in candidates:
            cursor = week_start(parse_date(candidate.harvest_start))
            last = week_start(parse_date(candidate.harvest_end))
            while cursor <= last:
                keys.add(cursor.isoformat())
                cursor += timedelta(weeks=1)
        for row in payload.demand:
            keys.add(week_key(parse_date(row.iso_week)))

        weeks = tuple(sorted(keys))
        week_index = {key: i for i, key in enumerate(weeks)}

        span = {
            c.id: (
                week_index[week_key(parse_date(c.harvest_start))],
                week_index[week_key(parse_date(c.harvest_end))],
            )
            for c in candidates
        }

        plot_refs = tuple(sorted({c.plot_ref for c in candidates}))
        by_plot = {
            ref: tuple(c for c in candidates if c.plot_ref == ref) for ref in plot_refs
        }

        demand_kg: dict[tuple[str, int], int] = {}
        for row in payload.demand:
            slot = (row.commodity_ref, week_index[week_key(parse_date(row.iso_week))])
            demand_kg[slot] = demand_kg.get(slot, 0) + row.kg

        return cls(
            weeks=weeks,
            week_index=week_index,
            candidates=candidates,
            by_id={c.id: c for c in candidates},
            by_plot=by_plot,
            plot_refs=plot_refs,
            span=span,
            demand_kg=demand_kg,
            capacity=payload.capacity_tonnes_per_week,
            objectives=tuple(payload.objectives),
            seed=payload.seed,
        )

    def weeks_of(self, candidate: Candidate) -> tuple[int, ...]:
        """Indeks setiap minggu yang disentuh jendela panen kandidat ini."""
        first, last = self.span[candidate.id]
        return tuple(range(first, last + 1))

    def week_share(self, candidate: Candidate, worst: bool) -> dict[int, float]:
        """Sebaran tonase kandidat ke minggu.

        Kasus terburuk menumpuk seluruh batas atas di titik tengah jendela —
        itu keadaan ketika cuaca menyeragamkan kematangan. Kasus harapan
        menyebar titik tengah rata sepanjang jendela.
        """
        weeks = self.weeks_of(candidate)
        if worst:
            return {weeks[len(weeks) // 2]: candidate.tonnes_high}
        return {w: candidate.tonnes_mid / len(weeks) for w in weeks}

    def select(self, candidate_ids: list[str]) -> tuple[Candidate, ...]:
        """Ambil kandidat menurut id, terurut, mengabaikan id yang tak dikenal."""
        return tuple(self.by_id[i] for i in sorted(candidate_ids) if i in self.by_id)
