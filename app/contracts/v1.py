"""Kontrak v1.0 antara Terrion_Backend (Go) dan layanan ini.

Pasangannya di sisi Go: internal/aiclient/contract.go.
Perubahan bentuk apa pun di sini harus disertai perubahan berkas emas kembar
di tests/fixtures/ dan di repo Go. Lihat docs/ARCHITECTURE.md §4.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1.0"
CONTRACT_MAJOR = "1"

MAX_CANDIDATES = 2000
# Panjang tujuan bahasa bebas. Cukup untuk satu-dua kalimat pengurus,
# cukup pendek untuk tidak membengkakkan prompt lapis tujuan.
MAX_GOAL_CHARS = 500
MAX_DEMAND_ROWS = 400

Ref = Annotated[str, Field(pattern=r"^[pkv][0-9]+$")]
ISODate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Objective = Literal["aman", "pendapatan", "pasar"]


class Base(BaseModel):
    """Dasar setiap model kontrak: abaikan field asing, tolak mutasi."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Season(Base):
    label: str
    start: ISODate
    end: ISODate


class Candidate(Base):
    """Satu opsi tanam: lahan ini, varietas ini, tanggal ini.

    Tidak ada field untuk nama, koordinat, desa, atau koperasi — dan itu
    disengaja. Lihat tests/test_no_personal_data.py.
    """

    id: Annotated[str, Field(pattern=r"^c[0-9]{3,5}$")]
    plot_ref: Ref
    area_ha: float = Field(gt=0)
    commodity_ref: Ref
    variety_ref: Ref
    planting_date: ISODate
    harvest_start: ISODate
    harvest_end: ISODate
    tonnes_low: float = Field(ge=0)
    tonnes_mid: float = Field(ge=0)
    tonnes_high: float = Field(ge=0)
    plausibility: Literal["plausible", "early", "late"]
    price_per_kg: float | None = None

    @model_validator(mode="after")
    def tonnage_is_ordered(self) -> "Candidate":
        """Tolak rentang tonase yang terbalik dan jendela panen yang terbalik."""
        if not self.tonnes_low <= self.tonnes_mid <= self.tonnes_high:
            raise ValueError(
                f"{self.id}: tonase tidak terurut "
                f"({self.tonnes_low}, {self.tonnes_mid}, {self.tonnes_high})"
            )
        if self.harvest_end < self.harvest_start:
            raise ValueError(f"{self.id}: jendela panen terbalik")
        return self


class DemandRow(Base):
    """Permintaan pembeli: sekian kilogram komoditas ini, pada minggu ini."""

    commodity_ref: Ref
    iso_week: ISODate
    kg: int = Field(ge=0)


class Observation(Base):
    """Slot perluasan v2 — belum dikirim di v1.0. Lihat ARCHITECTURE §4.4."""

    gdd_ratio: float
    area_ha: float
    mean_temp_c: float
    yield_index: float


class ProposeRequest(Base):
    contract_version: str
    request_id: str
    seed: int
    season: Season
    objectives: list[Objective] = Field(min_length=1, max_length=3)
    # Tujuan pengurus dalam bahasa biasa. Kosong berarti bobot bawaan;
    # terisi berarti lapis tujuan menerjemahkannya menjadi bobot.
    goal: str | None = Field(default=None, max_length=MAX_GOAL_CHARS)
    capacity_tonnes_per_week: float | None = None
    candidates: list[Candidate] = Field(max_length=MAX_CANDIDATES)
    demand: list[DemandRow] = Field(default_factory=list, max_length=MAX_DEMAND_ROWS)
    observations: list[Observation] | None = None

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> "ProposeRequest":
        """Dua kandidat dengan id sama membuat respons tidak bisa ditafsirkan."""
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("id kandidat tidak unik")
        return self


class Metrics(Base):
    peak_tonnes_p50: float
    peak_tonnes_p90: float
    total_tonnes: float
    gross_value: float | None
    demand_covered_kg: int


class PlanResult(Base):
    objective: Objective
    candidate_ids: list[str]
    metrics: Metrics
    narrative: str | None
    narrative_source: Literal["llm", "template", "none"]


class Diagnostics(Base):
    evaluations: int
    monte_carlo_draws: int
    objective_status: str
    degraded: list[str] = Field(default_factory=list)


class ProposeResponse(Base):
    contract_version: str = CONTRACT_VERSION
    request_id: str
    solver: Literal["cp-sat", "greedy"]
    solver_version: str
    elapsed_ms: int
    plans: list[PlanResult]
    diagnostics: Diagnostics
