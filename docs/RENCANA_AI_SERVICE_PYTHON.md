# Rencana Layanan AI — `Terrion_AI` (Python)

> Repo baru, dikerjakan terpisah dari `Terrion_Backend`.
> **Kontrak yang mengikat:** `ARSITEKTUR_SISTEM_TERRION.md` §4 (`v1.0`).
> **Pasangannya di sisi Go:** `RENCANA_BACKEND_INTEGRASI_AI.md`.
>
> Dokumen ini ditulis untuk dibaca oleh orang yang **tidak menyentuh repo Go
> sama sekali**. Satu-satunya hal yang perlu diambil dari sana adalah dua berkas
> JSON emas.

---

## Daftar Isi

- [0. Apa repo ini, dan apa yang bukan](#0-apa-repo-ini-dan-apa-yang-bukan)
- [1. Tumpukan teknologi dan pembenarannya](#1-tumpukan-teknologi-dan-pembenarannya)
- [2. Kerangka repo](#2-kerangka-repo)
- [3. Kontrak sebagai Pydantic](#3-kontrak-sebagai-pydantic)
- [4. Aplikasi FastAPI](#4-aplikasi-fastapi)
- [5. Solver — greedy dulu, CP-SAT kemudian](#5-solver--greedy-dulu-cp-sat-kemudian)
- [6. Ketidakpastian: Monte Carlo tiga titik](#6-ketidakpastian-monte-carlo-tiga-titik)
- [7. Lapis agen: narasi dengan penjaga numerik](#7-lapis-agen-narasi-dengan-penjaga-numerik)
- [8. Determinisme sebagai kewajiban kontrak](#8-determinisme-sebagai-kewajiban-kontrak)
- [9. Privasi yang diuji, bukan dijanjikan](#9-privasi-yang-diuji-bukan-dijanjikan)
- [10. Evaluasi: baseline, ambang, dan angka untuk juri](#10-evaluasi-baseline-ambang-dan-angka-untuk-juri)
- [11. Penyebaran](#11-penyebaran)
- [12. README dan model card](#12-readme-dan-model-card)
- [13. Urutan kerja](#13-urutan-kerja)
- [14. Yang tidak dikerjakan, dan alasannya](#14-yang-tidak-dikerjakan-dan-alasannya)

---

## 0. Apa repo ini, dan apa yang bukan

`Terrion_AI` adalah **layanan komputasi stateless**. Ia menerima soal
optimasi yang sudah jadi, menyelesaikannya, menjelaskannya dalam bahasa
Indonesia, dan mengembalikannya. Itu saja.

**Apa yang repo ini punya:**

- Solver kombinatorial (CP-SAT, dengan greedy sebagai cadangan internal)
- Propagasi ketidakpastian Monte Carlo
- Lapis agen LLM untuk narasi, dengan penjaga yang mencegahnya mengarang angka
- Harness evaluasi dengan baseline dan ambang yang ditetapkan **sebelum**
  hasilnya dilihat

**Apa yang repo ini tidak punya, dan tidak boleh punya:**

| Tidak punya | Kenapa |
| --- | --- |
| Koneksi basis data | Satu pemilik skema. Go memegang Postgres, titik. |
| Kredensial Supabase | Layanan ini tidak punya konsep pengguna. |
| Nama, NIK, koordinat, nama desa | Tipe payload tidak punya field-nya (§9). |
| Model fenologi/GDD atau model hasil panen | Itu lapis L1, hidup di Go, sudah teruji. Menyalinnya ke sini berarti dua sumber kebenaran untuk angka yang sama. |
| State antar permintaan | Dua permintaan identik wajib menghasilkan jawaban identik. Cache ada di Go. |
| Endpoint yang dipanggil peramban | Hanya Go yang memanggilnya, server-ke-server, dengan bearer token. |

Konsekuensi praktis yang paling penting bagi Anda: **Anda tidak diblokir oleh
siapa pun.** Yang Anda butuhkan untuk mulai adalah satu berkas,
`tests/fixtures/propose_request.golden.json`. Kalau berkas itu belum ada,
tulis sendiri dari `ARSITEKTUR_SISTEM_TERRION.md` §4.1 dan cocokkan nanti.

Sebaliknya juga berlaku: kalau repo ini tidak pernah selesai, fitur di Terrion
tetap jalan penuh dengan solver di dalam Go. Itu disengaja, dan itu yang
membuat kita berani menambah layanan kedua satu hari sebelum tenggat.

**Catatan gaya.** Aturan "tanpa komentar" di `Terrion_Backend/CLAUDE.md`
adalah aturan repo itu, bukan aturan universal. Di repo Python, docstring
singkat pada modul dan fungsi publik adalah idiom yang benar dan dipakai.
Yang tetap dilarang: komentar yang menjelaskan baris yang seharusnya cukup
dijelaskan oleh namanya, dan `TODO` yang tidak pernah dikerjakan.

---

## 1. Tumpukan teknologi dan pembenarannya

Guidebook, Ketentuan Peserta butir 5: *library maupun framework harus
didefinisikan peruntukannya pada dokumentasi proyek.* Tabel ini masuk apa
adanya ke `README.md`.

| Paket | Versi | Peruntukan | Kenapa ini, bukan yang lain |
| --- | --- | --- | --- |
| `fastapi` | ^0.115 | Kerangka HTTP | Validasi permintaan lewat Pydantic adalah *kontraknya* itu sendiri, bukan lapis tambahan. Flask akan memaksa validasi manual di setiap endpoint. |
| `uvicorn[standard]` | ^0.32 | Server ASGI | Standar de-facto untuk FastAPI; satu worker cukup dan justru diperlukan untuk determinisme. |
| `pydantic` | ^2.9 | Model kontrak `v1.0` | Satu sumber kebenaran untuk bentuk payload di sisi Python; `extra="ignore"` memberi kompatibilitas maju yang dituntut §4.4. |
| `pydantic-settings` | ^2.6 | Konfigurasi dari env | Menjaga pola "konfigurasi adalah satu objek, dibangun sekali" yang sama dengan sisi Go. |
| `ortools` | ^9.11 | Solver CP-SAT | Inti pekerjaan optimasi. Menulis branch-and-bound sendiri adalah pekerjaan berbulan-bulan yang hasilnya lebih buruk. |
| `numpy` | ^2.1 | Monte Carlo tervektorisasi | 2000 undian × 3 rencana selesai ~80 ms; loop Python murni butuh puluhan detik. |
| `httpx` | ^0.27 | Klien HTTP ke OpenRouter | Async, timeout eksplisit per permintaan — yang justru kita butuhkan untuk anggaran waktu §7. SDK OpenAI tidak dipakai: kita memanggil satu endpoint dengan satu bentuk badan, dan `httpx` sudah melakukannya tanpa menambah dependensi transitif. |
| `structlog` | ^24.4 | Log terstruktur JSON | `request_id` merambat dari Go ke log Python; tanpa ini, mengkorelasikan satu permintaan lintas dua layanan mustahil. |
| `pytest` | ^8.3 | Uji | — |
| `pytest-asyncio` | ^0.24 | Uji endpoint async | — |

Yang **sengaja tidak** dipakai, karena pertanyaan ini akan muncul:

- **Tanpa pandas.** Tidak ada tabel yang perlu di-*join*. NumPy sudah cukup, dan
  pandas menambah ~50 MB pada image.
- **Tanpa scikit-learn / PyTorch.** Tidak ada model yang dilatih di layanan ini.
  Pemodelan hasil panen ada di Go (§0). Menambahkannya hanya untuk terlihat
  seperti proyek AI adalah kebohongan yang mahal.
- **Tanpa LangChain.** Kita memanggil satu endpoint LLM dengan satu prompt
  tetap dan memvalidasi keluarannya. Abstraksi rantai menambah permukaan
  kegagalan tanpa menambah kemampuan.
- **Tanpa Celery/Redis.** Layanan ini sinkron dan stateless.

---

## 2. Kerangka repo

```
Terrion_AI/
├─ README.md
├─ pyproject.toml
├─ Dockerfile
├─ fly.toml
├─ .env.example
├─ .gitignore
├─ docs/
│  ├─ ARCHITECTURE.md            salinan ARSITEKTUR_SISTEM_TERRION.md
│  ├─ MODEL_CARD.md              apa yang boleh dan tidak boleh diklaim
│  └─ adr/                       salinan ADR yang menyentuh dua sisi
├─ app/
│  ├─ __init__.py
│  ├─ main.py                    FastAPI, lifespan, rute
│  ├─ config.py                  Settings (pydantic-settings)
│  ├─ security.py                dependency bearer token
│  ├─ logging.py                 structlog + request_id
│  ├─ contracts/
│  │  ├─ __init__.py
│  │  └─ v1.py                   ProposeRequest / ProposeResponse
│  ├─ problem.py                 Problem — bentuk internal turunan kontrak
│  ├─ solver/
│  │  ├─ __init__.py
│  │  ├─ objectives.py           bobot, normalisasi min-maks
│  │  ├─ metrics.py              puncak, nilai kotor, cakupan permintaan
│  │  ├─ greedy.py               solver cadangan internal
│  │  └─ cpsat.py                solver utama
│  ├─ risk/
│  │  ├─ __init__.py
│  │  └─ montecarlo.py           kuantil puncak mingguan
│  ├─ agent/
│  │  ├─ __init__.py
│  │  ├─ facts.py                fakta terhitung → blok prompt
│  │  ├─ guard.py                penjaga numerik
│  │  ├─ providers.py            openrouter | template
│  │  ├─ explain.py              orkestrasi + degradasi
│  │  └─ prompts/
│  │     └─ narrate_id.txt
│  └─ eval/
│     ├─ __init__.py
│     ├─ baselines.py
│     ├─ run.py                  CLI
│     └─ report.py
└─ tests/
   ├─ conftest.py
   ├─ test_contract_golden.py
   ├─ test_no_personal_data.py
   ├─ test_solver_determinism.py
   ├─ test_solver_quality.py
   ├─ test_metrics.py
   ├─ test_guard.py
   ├─ test_endpoint.py
   └─ fixtures/
      ├─ propose_request.golden.json     KEMBAR dengan repo Go
      ├─ propose_response.golden.json    KEMBAR dengan repo Go
      └─ subang_mt1.json                 soal berukuran nyata untuk evaluasi
```

### `pyproject.toml`

```toml
[project]
name = "terrion-ai"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "ortools>=9.11",
    "numpy>=2.1",
    "httpx>=0.27",
    "structlog>=24.4",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.7"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
target-version = "py312"
```

### `.env.example`

```
AI_SERVICE_TOKEN=
LLM_PROVIDER=template
LLM_API_KEY=
LLM_MODEL=meta-llama/llama-3.3-70b-instruct:free
LLM_FALLBACK_MODELS=deepseek/deepseek-chat-v3-0324:free,mistralai/mistral-small-3.2-24b-instruct:free
LLM_TIMEOUT_MS=2000
SOLVER_TIME_LIMIT_MS=1000
MONTE_CARLO_DRAWS=2000
LOG_LEVEL=INFO
```

`LLM_PROVIDER=template` sebagai bawaan disengaja: repo ini harus jalan penuh,
lulus seluruh uji, dan bisa didemokan **tanpa satu pun kunci API**. Penyedia
LLM adalah peningkatan opsional, sama seperti layanan ini sendiri adalah
peningkatan opsional bagi Go. Pola yang sama, dua tingkat.

---

## 3. Kontrak sebagai Pydantic

`app/contracts/v1.py` adalah satu-satunya tempat bentuk payload dinyatakan di
sisi Python. Tidak ada `dict` mentah yang menyeberangi batas HTTP.

```python
"""Kontrak v1.0. Pasangannya: Terrion_Backend/internal/aiclient/contract.go."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "1.0"
CONTRACT_MAJOR = "1"

MAX_CANDIDATES = 2000
MAX_DEMAND_ROWS = 400

Ref = Annotated[str, Field(pattern=r"^[pkv][0-9]+$")]
ISODate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]
Objective = Literal["aman", "pendapatan", "pasar"]


class Base(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)


class Season(Base):
    label: str
    start: ISODate
    end: ISODate


class Candidate(Base):
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
        if not self.tonnes_low <= self.tonnes_mid <= self.tonnes_high:
            raise ValueError(
                f"{self.id}: tonase tidak terurut "
                f"({self.tonnes_low}, {self.tonnes_mid}, {self.tonnes_high})"
            )
        if self.harvest_end < self.harvest_start:
            raise ValueError(f"{self.id}: jendela panen terbalik")
        return self


class DemandRow(Base):
    commodity_ref: Ref
    iso_week: ISODate
    kg: int = Field(ge=0)


class Observation(Base):
    """Slot perluasan v2 — belum dikirim di v1.0. Lihat ARSITEKTUR §4.4."""

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
    capacity_tonnes_per_week: float | None = None
    candidates: list[Candidate] = Field(max_length=MAX_CANDIDATES)
    demand: list[DemandRow] = Field(default_factory=list, max_length=MAX_DEMAND_ROWS)
    observations: list[Observation] | None = None

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> "ProposeRequest":
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
```

Dua keputusan yang layak disebut:

`frozen=True` pada seluruh model. Objek kontrak tidak boleh dimutasi setelah
diurai; setiap transformasi menghasilkan objek baru. Ini mematikan seluruh kelas
bug "seseorang mengubah `tonnes_mid` di tengah solver dan angka di respons tidak
lagi cocok dengan angka yang dipakai menghitung".

`Ref` divalidasi dengan regex `^[pkv][0-9]+$`. Kalau suatu hari Go keliru
mengirim UUID asli, permintaannya **ditolak dengan 422** alih-alih diterima
diam-diam. Batas privasi ditegakkan dari kedua arah, bukan hanya dari sisi
pengirim.

---

## 4. Aplikasi FastAPI

`app/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_service_token: str = ""
    llm_provider: str = "template"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    llm_fallback_models: str = ""
    llm_timeout_ms: int = 2000
    solver_time_limit_ms: int = 1000
    monte_carlo_draws: int = 2000
    log_level: str = "INFO"


settings = Settings()
```

`app/security.py`:

```python
import hmac

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.ai_service_token}"
    if not settings.ai_service_token or not hmac.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "unauthenticated", "message": ""}},
        )
```

`hmac.compare_digest`, bukan `==`. Perbandingan string biasa berhenti pada byte
pertama yang berbeda dan karena itu membocorkan panjang prefiks yang benar lewat
waktu eksekusi. Token yang kosong ditolak juga — layanan tanpa token yang
dikonfigurasi harus menolak semuanya, bukan menerima semuanya.

`app/main.py`:

```python
import time
import uuid

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.explain import narrate_all
from app.config import settings
from app.contracts.v1 import CONTRACT_MAJOR, CONTRACT_VERSION, ProposeRequest, ProposeResponse
from app.logging import bind_request, configure_logging, logger
from app.problem import Problem
from app.risk.montecarlo import peak_quantiles
from app.security import require_token
from app.solver import solve_all

configure_logging(settings.log_level)

app = FastAPI(title="Terrion AI", version="1.0.0", docs_url="/docs")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "terrion-ai"}


@app.get("/ready")
async def ready() -> dict[str, object]:
    from app.solver.cpsat import solver_available

    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "cpsat": solver_available(),
        "llm_provider": settings.llm_provider,
    }


@app.post("/v1/plan/propose", response_model=ProposeResponse,
          dependencies=[Depends(require_token)])
async def propose(payload: ProposeRequest, request: Request) -> ProposeResponse:
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or payload.request_id or str(uuid.uuid4())
    bind_request(request_id)

    if not payload.contract_version.startswith(f"{CONTRACT_MAJOR}."):
        return JSONResponse(
            status_code=409,
            content={"error": {
                "code": "contract_version_unsupported",
                "message": f"layanan berbicara {CONTRACT_VERSION}, "
                           f"permintaan {payload.contract_version}",
            }},
        )

    problem = Problem.from_request(payload)
    solutions, solver_name, status_name, evaluations = solve_all(problem, payload.seed)

    plans = []
    for objective, candidate_ids in solutions.items():
        chosen = problem.select(candidate_ids)
        p50, p90 = peak_quantiles(chosen, problem, settings.monte_carlo_draws, payload.seed)
        plans.append(problem.result(objective, chosen, p50, p90))

    plans, degraded = await narrate_all(plans, problem)

    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info("propose", candidates=len(payload.candidates),
                solver=solver_name, elapsed_ms=elapsed, degraded=degraded)

    return ProposeResponse(
        request_id=request_id,
        solver=solver_name,
        solver_version="1.0.0",
        elapsed_ms=elapsed,
        plans=plans,
        diagnostics=Diagnostics(
            evaluations=evaluations,
            monte_carlo_draws=settings.monte_carlo_draws,
            objective_status=status_name,
            degraded=degraded,
        ),
    )
```

`app/logging.py` mengikat `request_id` ke seluruh baris log berikutnya lewat
`structlog.contextvars`. Efeknya: satu permintaan bisa ditelusuri dari log Go ke
log Python dengan satu `grep`. Pada sistem dua layanan, ini bukan kemewahan.

---

## 5. Solver — greedy dulu, CP-SAT kemudian

### 5.1 Bentuk internal

`app/problem.py` menerjemahkan kontrak menjadi bentuk yang nyaman untuk
optimasi, dan **di sinilah seluruh aritmetika tanggal terjadi**, sekali saja:

```python
@dataclass(frozen=True)
class Problem:
    weeks: tuple[str, ...]                       # Senin ISO, urut
    week_index: dict[str, int]
    candidates: tuple[Candidate, ...]            # urut menurut id
    by_plot: dict[str, tuple[Candidate, ...]]    # urut menurut plot_ref lalu id
    plot_refs: tuple[str, ...]                   # urut
    demand_kg: dict[tuple[str, int], int]        # (commodity_ref, minggu) -> kg
    capacity: float | None
    objectives: tuple[str, ...]
```

Setiap koleksi adalah `tuple` dan setiap urutan ditetapkan eksplisit. Tidak ada
satu pun titik di solver yang mengiterasi `dict` yang urutannya bergantung pada
urutan sisipan dari sumber luar. Ini prasyarat §8.

Sebaran tonase satu kandidat ke minggu:

```python
def week_share(candidate: Candidate, problem: Problem, worst: bool) -> dict[int, float]:
    """Kasus terburuk menumpuk di titik tengah jendela; kasus harapan menyebar rata."""
    weeks = problem.weeks_between(candidate.harvest_start, candidate.harvest_end)
    if worst:
        return {weeks[len(weeks) // 2]: candidate.tonnes_high}
    return {w: candidate.tonnes_mid / len(weeks) for w in weeks}
```

Kedua bentuk linear terhadap variabel keputusan, jadi keduanya bisa masuk ke
CP-SAT tanpa trik.

### 5.2 Tiga objektif

`app/solver/objectives.py`:

```python
WEIGHTS: dict[str, tuple[float, float, float]] = {
    "aman":       (0.70, 0.20, 0.10),
    "pendapatan": (0.15, 0.75, 0.10),
    "pasar":      (0.20, 0.20, 0.60),
}

USES_WORST_CASE = {"aman": True, "pendapatan": False, "pasar": False}
```

Urutan bobot: (ratakan puncak, maksimalkan pendapatan, penuhi permintaan).

Normalisasi min-maks memakai rentang yang **benar-benar dicapai**, bukan
rentang teoretis: jalankan greedy murni untuk masing-masing dari tiga tujuan
tunggal, catat nilai puncak/pendapatan/cakupan yang muncul, dan pakai itu
sebagai batas. Batas teoretis (`0` sampai `total seluruh tonase`) akan membuat
seluruh skor menempel di ujung yang sama dan bobot kehilangan artinya.

Rencana "aman" diskor pada **puncak kasus terburuk**, bukan pada nilai harapan.
Ini bukan detail implementasi, ini definisi kata "aman": rencana yang aman
adalah rencana yang tetap muat di gudang ketika panen datang lebih cepat dan
lebih banyak dari perkiraan. Menskornya pada nilai harapan berarti menamainya
"aman" sambil mengoptimalkan hal lain.

### 5.3 Greedy — dikerjakan hari pertama

`app/solver/greedy.py`. Ini cermin dari `planning.Search` di Go, dan
kesamaannya bukan kebetulan: ia yang membuat kedua mesin bisa dibandingkan di
harness evaluasi (§10).

```python
def greedy(problem: Problem, objective: str, bounds: Bounds) -> list[str]:
    chosen: list[Candidate] = []

    for plot_ref in problem.plot_refs:
        best: Candidate | None = None
        best_score = float("-inf")

        for candidate in problem.by_plot[plot_ref]:
            score = scalarise(measure(chosen + [candidate], problem, objective),
                              objective, bounds)
            if score > best_score + 1e-12:
                best, best_score = candidate, score

        if best is not None:
            chosen.append(best)

    return [c.id for c in chosen]


def improve(problem: Problem, objective: str, bounds: Bounds,
            chosen: list[Candidate], passes: int = 3) -> list[Candidate]:
    for _ in range(passes):
        moved = False
        for position, current in enumerate(chosen):
            for alternative in problem.by_plot[current.plot_ref]:
                if alternative.id == current.id:
                    continue
                trial = list(chosen)
                trial[position] = alternative
                if scalarise(measure(trial, problem, objective), objective, bounds) > \
                   scalarise(measure(chosen, problem, objective), objective, bounds) + 1e-12:
                    chosen, moved = trial, True
        if not moved:
            break
    return chosen
```

`+ 1e-12` pada setiap perbandingan disengaja: tanpa toleransi, dua skor yang
secara matematis sama tetapi berbeda pada bit terakhir akan memilih pemenang
yang berbeda tergantung urutan penjumlahan floating point. Itu adalah kebocoran
determinisme yang paling sulit ditemukan, dan ia akan muncul persis saat demo.

### 5.4 CP-SAT — dikerjakan menjelang final

`app/solver/cpsat.py`:

```python
from ortools.sat.python import cp_model

SCALE = 1000  # ton -> kg, supaya seluruh model berbilangan bulat


def solve(problem: Problem, objective: str, bounds: Bounds, seed: int, time_limit_ms: int):
    model = cp_model.CpModel()
    x = {c.id: model.NewBoolVar(c.id) for c in problem.candidates}

    for plot_ref in problem.plot_refs:
        model.AddAtMostOne(x[c.id] for c in problem.by_plot[plot_ref])

    worst = USES_WORST_CASE[objective]
    total_kg = sum(int(c.tonnes_high * SCALE) for c in problem.candidates)
    peak = model.NewIntVar(0, total_kg, "peak")

    for week in range(len(problem.weeks)):
        terms = [
            int(kg * SCALE) * x[c.id]
            for c in problem.candidates
            for w, kg in week_share(c, problem, worst).items()
            if w == week
        ]
        if terms:
            model.Add(peak >= sum(terms))

    income = sum(int((c.price_per_kg or 0) * c.tonnes_mid * SCALE) * x[c.id]
                 for c in problem.candidates)
    covered = coverage_expression(model, problem, x)

    w_peak, w_income, w_market = WEIGHTS[objective]
    model.Maximize(
        - normalised(w_peak, peak, bounds.peak)
        + normalised(w_income, income, bounds.income)
        + normalised(w_market, covered, bounds.coverage)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_ms / 1000
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise SolverFailed(solver.StatusName(status))

    return (
        [c.id for c in problem.candidates if solver.Value(x[c.id])],
        solver.StatusName(status),
        solver.NumBranches(),
    )
```

`num_search_workers = 1` mengorbankan paralelisme demi determinisme. Pada soal
sebesar ini (ratusan variabel biner), solver selesai dalam puluhan milidetik dan
paralelisme tidak memberi apa-apa; determinisme memberi segalanya (§8).

`AddAtMostOne`, bukan `AddExactlyOne` — sebuah lahan boleh tidak ditanami
sama sekali kalau tidak ada opsi yang memperbaiki skor. Memaksa `ExactlyOne`
akan menghasilkan rencana yang selalu memenuhi seluruh lahan bahkan ketika itu
merugikan, yang persis kesalahan yang fitur ini ada untuk menghindarinya.

**Cadangan internal.** `app/solver/__init__.py`:

```python
def solve_all(problem, seed):
    bounds = derive_bounds(problem)
    try:
        return _with_cpsat(problem, bounds, seed)
    except (ImportError, SolverFailed) as exc:
        logger.warning("cpsat_unavailable", reason=str(exc))
        return _with_greedy(problem, bounds, seed)
```

`ImportError` ditangkap karena roda `ortools` berukuran ~50 MB dan sebagian
tingkat gratis menolaknya. Layanan tetap berguna tanpanya, hanya sedikit lebih
lemah — pola degradasi yang sama, tingkat ketiga.

---

## 6. Ketidakpastian: Monte Carlo tiga titik

Kontrak memberi tiga angka per kandidat: `tonnes_low`, `tonnes_mid`,
`tonnes_high`, plus jendela panen `[harvest_start, harvest_end]`. Solver
memakai satu angka saja. Sisanya adalah informasi yang dibuang, dan justru di
sanalah risikonya berada.

Distribusi segitiga adalah distribusi kanonik untuk estimasi tiga titik —
ia tidak menambah asumsi apa pun di luar tiga angka yang sudah kita punya.
Distribusi normal akan menuntut kita mengarang sebuah simpangan baku;
distribusi seragam akan membuang informasi bahwa `mid` lebih mungkin daripada
ujung.

`app/risk/montecarlo.py`:

```python
import numpy as np


def peak_quantiles(chosen, problem, draws, seed) -> tuple[float, float]:
    if not chosen:
        return 0.0, 0.0

    rng = np.random.default_rng(seed)
    n = len(chosen)

    starts = np.array([problem.week_index[c.harvest_start_week] for c in chosen])
    ends = np.array([problem.week_index[c.harvest_end_week] for c in chosen])
    low = np.array([c.tonnes_low for c in chosen])
    mid = np.array([c.tonnes_mid for c in chosen])
    high = np.array([c.tonnes_high for c in chosen])

    week = rng.integers(starts, ends + 1, size=(draws, n))
    tonnes = triangular_icdf(rng.random((draws, n)), low, mid, high)

    totals = np.zeros((draws, len(problem.weeks)))
    np.add.at(totals, (np.arange(draws)[:, None], week), tonnes)

    peak = totals.max(axis=1)
    return float(np.percentile(peak, 50)), float(np.percentile(peak, 90))


def triangular_icdf(u, low, mid, high):
    span = np.where(high > low, high - low, 1e-9)
    pivot = (mid - low) / span
    left = low + np.sqrt(u * span * (mid - low))
    right = high - np.sqrt((1 - u) * span * (high - mid))
    return np.where(u < pivot, left, right)
```

Dua sifat yang membuat ini layak dipakai, bukan hanya terlihat canggih:

**Ia menjawab pertanyaan yang benar-benar ditanyakan pengurus koperasi.**
"Berapa ton paling banyak yang mungkin datang dalam satu minggu?" bukan
"berapa rata-ratanya". `peak_tonnes_p90` adalah angka yang menentukan apakah
gudang cukup, dan tidak ada cara mendapatkannya dari nilai harapan.

**Ia jujur soal apa yang tidak ia tangkap.** Undian per kandidat bersifat
independen. Kenyataannya, cuaca berkorelasi: kalau musim datang terlambat, ia
terlambat untuk semua lahan sekaligus, dan P90 yang sesungguhnya lebih buruk
dari yang dihitung di sini. Ini masuk `MODEL_CARD.md` sebagai keterbatasan yang
dinyatakan, bukan sebagai hal yang disembunyikan sampai ada juri yang
menemukannya. Perbaikannya (satu faktor pergeseran musim bersama per undian)
adalah tiga baris, dan dicatat sebagai pekerjaan v2.

`peak_tonnes_p50` dan `p90` inilah yang mengisi `Metrics` di respons. Go akan
menghitung ulang metriknya sendiri dan **tidak memakai angka ini untuk
apa pun yang dilihat pengguna** — ia masuk log untuk perbandingan. Itu bukan
pemborosan: ia adalah satu-satunya cara membandingkan dua mesin secara jujur di
§10.

---

## 7. Lapis agen: narasi dengan penjaga numerik

### 7.1 Masalahnya

Model bahasa yang diminta menjelaskan sebuah rencana akan menghasilkan kalimat
yang enak dibaca dan, cepat atau lambat, sebuah angka yang tidak pernah dihitung
siapa pun. Pada aplikasi hiburan itu memalukan. Pada aplikasi yang dipakai
pengurus koperasi untuk memutuskan apa yang ditanam 200 keluarga, itu tidak bisa
diterima.

Jawaban yang biasa — "kami menulis prompt yang melarangnya" — adalah harapan.
Jawaban di sini adalah pemeriksaan mekanis.

### 7.2 Struktur dua bagian

`app/agent/facts.py` menyusun blok fakta dari angka yang **sudah dihitung**:

```python
@dataclass(frozen=True)
class Facts:
    objective: str
    plots: int
    varieties: tuple[str, ...]
    first_harvest_week: str
    last_harvest_week: str
    peak_p50: float
    peak_p90: float
    capacity: float | None
    total_tonnes: float
    demand_covered_kg: int

    def block(self) -> str:
        ...

    def allowed_numbers(self) -> frozenset[str]:
        """Setiap angka yang boleh muncul di narasi, dalam bentuk tercetaknya."""
```

`allowed_numbers()` mengembalikan representasi tercetak dari setiap angka di
blok fakta — `"7"`, `"11,8"`, `"12,5"`, dan komponen setiap tanggal — dan tidak
ada yang lain.

`app/agent/guard.py`:

```python
import re

NUMBER = re.compile(r"\d[\d.,]*")


def numbers_are_grounded(text: str, allowed: frozenset[str]) -> bool:
    for match in NUMBER.finditer(text):
        token = match.group().rstrip(".,")
        if token not in allowed:
            return False
    return True
```

Penjaga ini **ketat**: satu token angka yang tidak ada di daftar membatalkan
seluruh narasi, dan `explain.py` jatuh ke templat.

Ketat adalah pilihan yang benar di sini, dan alasannya bukan estetika. Biaya
salah-tolak adalah kalimat templat yang sedikit kaku. Biaya salah-terima adalah
angka karangan yang dibaca sebagai hasil perhitungan sistem. Ketika biaya kedua
jenis galat setimpang seperti ini, ambang tidak diletakkan di tengah.

Konsekuensi yang diterima dengan sadar: prompt harus melarang model menulis
angka apa pun yang tidak ada di blok fakta — termasuk "5 lahan" kalau `5` tidak
ada di sana. Tingkat penolakan awal akan tinggi. Ukur dan laporkan di
`MODEL_CARD.md`; jangan melonggarkan penjaga untuk menurunkannya.

### 7.3 Prompt

`app/agent/prompts/narrate_id.txt`:

```
Kamu menulis satu paragraf untuk pengurus koperasi tani di Indonesia.

FAKTA (satu-satunya sumber angka yang boleh kamu pakai):
{facts}

ATURAN
- Tulis 2-4 kalimat bahasa Indonesia yang wajar, bukan daftar.
- Jelaskan mengapa rencana ini masuk akal untuk tujuan "{objective}".
- Kamu hanya boleh menulis angka yang persis muncul di blok FAKTA.
  Jangan menghitung, menjumlahkan, membulatkan, atau memperkirakan apa pun.
- Jangan menyebut nama orang, desa, atau koordinat. Kamu tidak memilikinya.
- Jangan menjanjikan hasil. Ini proyeksi, bukan kepastian.

Tulis paragrafnya saja, tanpa judul dan tanpa pembuka.
```

### 7.4 Penyedia dan degradasi

`app/agent/providers.py` menyediakan **dua**, dipilih lewat `LLM_PROVIDER`:

| Nilai | Perilaku |
| --- | --- |
| `template` | **bawaan.** Kalimat Indonesia dirakit dari `Facts` dengan f-string. Tanpa jaringan, tanpa kunci, deterministik. |
| `openrouter` | `httpx.AsyncClient` ke `https://openrouter.ai/api/v1/chat/completions`, skema OpenAI, `temperature=0.2`, `seed` dari permintaan. |

Dua penyedia, bukan empat, karena **OpenRouter sudah berupa router**. Satu
kunci, satu URL dasar, satu bentuk permintaan; berganti dari Llama ke DeepSeek
ke Mistral adalah mengubah satu variabel lingkungan, bukan menulis kelas baru.
Menambahkan `groq` dan `gemini` sebagai kelas terpisah berarti menulis tiga
adaptor untuk masalah yang sudah diselesaikan oleh satu.

```python
class OpenRouter:
    is_remote = True

    async def narrate(self, facts: Facts) -> str:
        payload = {
            "model": settings.llm_model,
            "models": _fallback_models(),
            "temperature": 0.2,
            "seed": facts.seed,
            "max_tokens": 220,
            "messages": [{"role": "user", "content": render_prompt(facts)}],
        }
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "HTTP-Referer": "https://github.com/ITechnoCup2026",
            "X-Title": "Terrion",
        }
        async with httpx.AsyncClient(base_url=settings.llm_base_url) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
```

Field `models` adalah daftar cadangan bawaan OpenRouter: kalau model pertama
kehabisan kuota atau sedang tumbang, permintaan yang sama dilayani model
berikutnya tanpa satu baris kode pun di pihak kita. Ini yang membuat OpenRouter
lebih tepat daripada memanggil satu penyedia langsung — kuota tingkat gratis
habis persis pada hari demo, dan itu bukan hari yang baik untuk menulis logika
cadangan.

**Empat hal yang harus diketahui sebelum mengandalkannya**, dan tidak satu pun
mengubah keputusan:

1. **Latensi model gratis tidak dijamin.** Permintaan ke model `:free` bisa
   memakan 5–15 detik saat antreannya panjang, jauh melewati anggaran 2 detik
   di §7.4. Konsekuensinya: sebagian narasi akan berupa templat, dan itu
   memang perilaku yang dirancang. Ukur berapa sering, laporkan di model card,
   jangan naikkan anggarannya — anggaran itu melindungi permintaan pengguna.
2. **Kuota tingkat gratis terbatas dan berubah.** Periksa halaman *Limits* di
   akun OpenRouter sebelum demo; angkanya berubah dari waktu ke waktu. Karena
   respons di-cache 6 jam di Redis sisi Go, satu demo hanya memakai beberapa
   panggilan.
3. **`seed` tidak dijamin dihormati** oleh setiap model di belakang router.
   Determinisme sistem tetap utuh karena cache Go mengembalikan narasi yang sama
   untuk permintaan yang sama, dan karena penjaga numerik §7.2 menjamin
   *kebenaran* isinya terlepas dari kata-katanya. Yang tidak kita klaim: bahwa
   kalimatnya identik kata per kata di dua panggilan cache-miss.
4. **Kebijakan data.** Sebagian model gratis di OpenRouter memakai prompt untuk
   pelatihan kecuali disetel sebaliknya di *Settings → Privacy*. Setel sesuai
   keinginan Anda — tetapi perhatikan bahwa **ini tidak mengubah paparan kita**:
   blok fakta hanya berisi jumlah, ton, dan tanggal, dan `test_the_prompt_never_
   receives_a_reference` (§9) menjamin bahkan referensi buram pun tidak ikut.
   Inilah manfaat konkret pertama dari batas §9 — kita bisa memakai penyedia
   tingkat gratis tanpa memperdebatkan kebijakan datanya.

`app/agent/explain.py` menegakkan urutannya:

```python
async def narrate_all(plans, problem) -> tuple[list[PlanResult], list[str]]:
    degraded: list[str] = []
    provider = get_provider(settings.llm_provider)
    out = []

    for plan in plans:
        facts = Facts.from_plan(plan, problem)
        text, source = template_narrative(facts), "template"

        if provider.is_remote:
            try:
                candidate = await asyncio.wait_for(
                    provider.narrate(facts), timeout=settings.llm_timeout_ms / 1000)
                if numbers_are_grounded(candidate, facts.allowed_numbers()):
                    text, source = candidate, "llm"
                else:
                    degraded.append(f"{plan.objective}:ungrounded_numbers")
            except (asyncio.TimeoutError, httpx.HTTPError) as exc:
                degraded.append(f"{plan.objective}:llm_unavailable")
                logger.warning("llm_failed", objective=plan.objective, error=str(exc))

        out.append(plan.model_copy(update={"narrative": text, "narrative_source": source}))

    return out, degraded
```

Perhatikan urutannya: **templat dibuat lebih dulu**, LLM hanya boleh
menggantikannya. Tidak ada jalur di fungsi ini yang bisa berakhir tanpa narasi.

Ini juga yang membuat ADR-0005 aman. Solver dan narasi memang berbagi satu
panggilan HTTP, tetapi anggaran waktu LLM terpisah dan dibatasi
`asyncio.wait_for`, sehingga kegagalannya secara struktural tidak bisa
membatalkan hasil solver yang sudah ada di tangan.

### 7.5 Yang sengaja tidak dibangun sekarang

Penerjemahan niat bahasa alami ("saya mau fokus jual ke pasar bulan Januari"
→ batasan solver) adalah lapis agen yang sebenarnya, dan ia menunggu sampai
setelah final. Kalau dibangun, bentuknya sudah ditetapkan: keluaran LLM diurai
menjadi model Pydantic dengan daftar putih ketat, batasan yang tidak dikenali
**ditolak, bukan diabaikan**, dan hasil terjemahannya ditampilkan ke pengguna
untuk dikonfirmasi sebelum dijalankan. Agen tidak pernah mengeksekusi diam-diam
apa yang ia kira dimaksud pengguna.

---

## 8. Determinisme sebagai kewajiban kontrak

`ARSITEKTUR_SISTEM_TERRION.md` ADR-0007 menjadikan determinisme bagian dari
kontrak, bukan sifat yang mudah-mudahan ada. Alasannya dua, dan yang kedua lebih
penting daripada yang pertama:

1. Cache di sisi Go hanya bekerja kalau permintaan yang sama menghasilkan
   jawaban yang sama.
2. **Pengurus koperasi yang membuka layar yang sama dua kali dan melihat dua
   rencana berbeda tidak akan mempercayai sistemnya lagi** — dan ia benar untuk
   tidak mempercayainya. Sistem yang tidak bisa mengulangi jawabannya juga tidak
   bisa diaudit, tidak bisa didebug, dan tidak bisa dipertanggungjawabkan ketika
   panennya meleset.

Lima sumber non-determinisme di layanan ini, dan penutupannya:

| Sumber | Penutup |
| --- | --- |
| Iterasi `dict` atas data dari luar | `Problem` menyimpan `tuple` terurut; solver tidak pernah mengiterasi `dict` masukan |
| Paralelisme CP-SAT | `num_search_workers = 1`, `random_seed = payload.seed` |
| Undian Monte Carlo | `np.random.default_rng(seed)` per permintaan, tidak pernah RNG global |
| Perbandingan floating point | toleransi `1e-12` di setiap `>` yang memilih pemenang |
| Suhu LLM | `temperature=0.2` + `seed`; dan kalaupun tetap berbeda, penjaga §7.2 menjamin isinya tetap benar |

Ujinya, dan ini uji yang dibacakan ke juri:

```python
def test_two_identical_requests_produce_identical_responses(client, golden_request):
    first = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()
    second = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()

    for body in (first, second):
        body.pop("elapsed_ms")
        body.pop("request_id")

    assert first == second


def test_a_different_seed_may_change_the_plan_but_not_its_validity(client, golden_request):
    other = golden_request | {"seed": golden_request["seed"] + 1}
    body = client.post("/v1/plan/propose", json=other, headers=AUTH).json()

    for plan in body["plans"]:
        assert len(set(plan["candidate_ids"])) == len(plan["candidate_ids"])
        assert plan["metrics"]["peak_tonnes_p90"] >= plan["metrics"]["peak_tonnes_p50"]
```

`elapsed_ms` dan `request_id` dikecualikan — keduanya memang tidak deterministik,
dan keduanya sudah dikecualikan dari kunci cache di sisi Go.

---

## 9. Privasi yang diuji, bukan dijanjikan

Guidebook, Ketentuan Peserta butir 7, mewajibkan perlindungan data pengguna dan
penjagaan privasi dalam penggunaan AI. Ini pertanyaan yang hampir pasti muncul
di sesi tanya jawab final.

Jawaban Terrion punya tiga lapis, dan tidak satu pun berupa kebijakan tertulis.

**Lapis 1 — bentuk tipe.** `Candidate` tidak punya field untuk nama, koordinat,
desa, atau pengenal koperasi. Data pribadi tidak disaring; ia tidak punya tempat
untuk berada.

**Lapis 2 — referensi buram per-permintaan.** `p1`, `k1`, `v3` dibangkitkan
ulang oleh Go pada setiap permintaan. Layanan ini — bahkan kalau seluruh lognya
disimpan selamanya — tidak bisa merakit riwayat satu lahan tertentu, karena `p1`
hari ini dan `p1` besok bukan lahan yang sama. Regex `^[pkv][0-9]+$` di `Ref`
menolak UUID asli dengan `422`, sehingga batas ini ditegakkan juga dari sisi
penerima.

**Lapis 3 — uji yang gagal kalau ada yang mencoba.**

`tests/test_no_personal_data.py`:

```python
from app.contracts.v1 import Candidate, ProposeRequest

FIELD_KANDIDAT_YANG_DIIZINKAN = {
    "id", "plot_ref", "area_ha", "commodity_ref", "variety_ref",
    "planting_date", "harvest_start", "harvest_end",
    "tonnes_low", "tonnes_mid", "tonnes_high",
    "plausibility", "price_per_kg",
}


def test_candidate_carries_nothing_beyond_the_whitelist():
    assert set(Candidate.model_fields) == FIELD_KANDIDAT_YANG_DIIZINKAN, (
        "Bentuk Candidate berubah. Setiap field baru di sini adalah data yang akan "
        "meninggalkan sistem Terrion menuju layanan ini dan mungkin menuju penyedia "
        "LLM. Kalau penambahan ini disengaja, ubah daftar putih pada commit yang sama "
        "dan jelaskan di docs/ARCHITECTURE.md kenapa field itu bukan data pribadi."
    )


def test_references_must_not_be_uuids(golden_request):
    rusak = deepcopy(golden_request)
    rusak["candidates"][0]["plot_ref"] = "11111111-1111-4111-8111-111111111111"

    with pytest.raises(ValidationError):
        ProposeRequest.model_validate(rusak)


def test_the_prompt_never_receives_a_reference(monkeypatch, golden_request):
    terlihat: list[str] = []
    monkeypatch.setattr(
        "app.agent.providers.Remote.narrate",
        lambda self, facts: terlihat.append(facts.block()) or "",
    )

    ...

    for blok in terlihat:
        assert not re.search(r"\b[pkv]\d+\b", blok), (
            "blok fakta membocorkan referensi ke penyedia LLM"
        )
```

Uji ketiga menutup lubang yang mudah terlewat: referensi buram memang tidak
mengidentifikasi siapa pun, tetapi tidak ada alasan penyedia LLM pihak ketiga
perlu melihatnya sama sekali. Narasi berbicara tentang jumlah dan minggu, bukan
tentang lahan bernomor.

---

## 10. Evaluasi: baseline, ambang, dan angka untuk juri

Bagian yang paling sering hilang dari proyek AI kompetisi, dan yang paling
membedakan ketika ada juri bertanya "dari mana Anda tahu ini lebih baik?".

**Ambang ditetapkan sekarang, sebelum satu angka pun dilihat.** Ini bukan
formalitas — ambang yang ditetapkan setelah melihat hasil adalah ambang yang
dipilih agar hasilnya lulus.

### 10.1 Baseline

`app/eval/baselines.py`, empat, dari yang paling lemah:

| Baseline | Definisi | Guna |
| --- | --- | --- |
| `status_quo` | setiap lahan menanam varietas terakhirnya pada tanggal paling awal yang layak | inilah yang sebenarnya terjadi hari ini di koperasi; pembanding yang jujur |
| `random` | pilihan acak ber-seed, 20 ulangan, dilaporkan sebagai rerata ± sd | membuktikan solver mengerjakan sesuatu, bukan beruntung |
| `greedy` | greedy murni tanpa local search | mengukur kontribusi local search |
| `cpsat` | solver utama | — |

### 10.2 Metrik dan ambang

| Metrik | Pembanding | Ambang lulus | Kalau tidak tercapai |
| --- | --- | --- | --- |
| Penurunan puncak mingguan P90 (objektif `aman`) | `status_quo` | **≥ 20%** | laporkan apa adanya; jangan ubah ambangnya |
| Nilai kotor (objektif `pendapatan`) | `status_quo` | **≥ +8%** | idem |
| Cakupan permintaan kg (objektif `pasar`) | `status_quo` | **≥ +25%** | idem |
| Skor terskalarisasi `cpsat` vs `greedy` | `greedy` | **≥ +3%** | kalau tidak, katakan CP-SAT tidak berkontribusi dan pakai greedy — itu temuan, bukan kegagalan |
| Waktu solve p95 | — | **≤ 1,5 s** | turunkan `SOLVER_TIME_LIMIT_MS` |
| Determinisme | — | **100% identik** | ini pemblokir rilis, bukan metrik |
| Narasi lolos penjaga numerik | — | dilaporkan, tanpa ambang | angka ini masuk model card apa adanya |

### 10.3 CLI

```bash
python -m app.eval.run tests/fixtures/subang_mt1.json --draws 2000 --repeats 20
```

Keluarannya satu tabel Markdown yang bisa langsung ditempel ke `MODEL_CARD.md`
dan ke slide pitching. Itulah bentuk keluaran yang benar untuk harness evaluasi:
sesuatu yang dibaca manusia dan dibawa ke ruang presentasi.

### 10.4 Yang harus dikatakan apa adanya

Dua keterbatasan yang **wajib** disebut sendiri sebelum juri menemukannya.
Menyebutkannya lebih dulu adalah tanda bahwa kita memahami sistem kita; menunggu
ditemukan adalah tanda sebaliknya.

1. **Panel harga acuan di basis data saat ini sintetis.** Ia dibangkitkan oleh
   `round(harga_dasar + amplitudo * sin(2π × hari_dalam_tahun / 365))` di migrasi
   seed, dengan sumber tercatat `'SINTETIS — ganti dengan panel harga Badan
   Pangan Nasional'`. Artinya objektif `pendapatan` saat ini mengoptimalkan
   terhadap sebuah gelombang sinus. Struktur optimasinya benar dan angkanya
   langsung menjadi bermakna begitu panel harga nyata masuk, tetapi selisih
   pendapatan yang dilaporkan hari ini **tidak boleh dibacakan sebagai rupiah
   nyata**.

2. **Undian Monte Carlo independen antar lahan.** Cuaca berkorelasi; musim yang
   terlambat terlambat untuk semua orang. P90 yang dilaporkan karena itu
   optimistis. Perbaikannya sudah diketahui (satu faktor pergeseran musim
   bersama per undian) dan dicatat sebagai pekerjaan v2.

---

## 11. Penyebaran

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY app ./app

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

`--workers 1` bukan penghematan memori semata: dua worker berarti dua proses
dengan state RNG berbeda, dan itu melanggar §8.

### `fly.toml`

```toml
app = "terrion-ai"
primary_region = "sin"

[build]

[env]
  LOG_LEVEL = "INFO"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 0

  [[http_service.checks]]
    interval = "30s"
    timeout = "5s"
    grace_period = "10s"
    method = "GET"
    path = "/health"

[[vm]]
  memory = "512mb"
  cpu_kind = "shared"
  cpus = 1
```

`primary_region = "sin"` (Singapura) — terdekat dengan pengguna Indonesia dan
dengan region Supabase yang lazim dipakai. Latensi Go→Python di region yang sama
sekitar 5 ms; lintas benua bisa 200 ms, yang memakan seperlima anggaran 3,5 detik
untuk hal yang bisa dihindari dengan satu baris konfigurasi.

`min_machines_running = 0` dengan `auto_start_machines` — mesin tidur saat tidak
dipakai dan bangun ~1–2 detik saat dipanggil. Itu masuk anggaran; dan kalau
ternyata tidak, permintaan pertama jatuh ke fallback Go dan yang kedua berhasil.
Tidak ada yang rusak.

```bash
fly launch --no-deploy
fly secrets set AI_SERVICE_TOKEN=$(openssl rand -hex 32)
fly secrets set LLM_PROVIDER=template
# menjelang final, setelah §7.4 selesai:
# fly secrets set LLM_PROVIDER=openrouter LLM_API_KEY=sk-or-v1-...
fly deploy
```

Token yang sama diset di sisi Go sebagai `AI_SERVICE_TOKEN`, dan
`AI_SERVICE_URL` diisi `https://terrion-ai.fly.dev`.

**Alternatif kalau Fly.io bermasalah:** Render (tidur setelah 15 menit, bangun
~30 detik — masih baik-baik saja karena ada fallback) atau Hugging Face Spaces
dengan SDK Docker. Kalau ketiganya gagal, biarkan `AI_SERVICE_URL` kosong dan
sertakan instruksi `docker compose up` di README supaya juri bisa menjalankannya
sendiri. Tidak ada skenario di mana ini memblokir pengumpulan.

---

## 12. README dan model card

`README.md` mengikuti template ITechno Cup yang sama dengan repo Go — lima
bagian wajib — dengan penyesuaian bahwa repo ini layanan, bukan situs:

1. **Penjelasan aplikasi** — peran layanan ini di dalam Terrion, dengan diagram
   kontainer Mermaid dari `ARSITEKTUR_SISTEM_TERRION.md` §3.
2. **Fitur utama** — solver CP-SAT tiga objektif, kuantil risiko Monte Carlo,
   narasi berpenjaga numerik, batas nol-data-pribadi.
3. **Teknologi yang digunakan** — tabel §1 dokumen ini apa adanya, termasuk kolom
   "kenapa ini, bukan yang lain" dan daftar yang sengaja tidak dipakai.
4. **Cara instalasi** — `pip install -e ".[dev]"`, `cp .env.example .env`.
5. **Cara penggunaan** — `uvicorn app.main:app --reload`, satu contoh `curl`
   lengkap memakai berkas emas, `pytest`, dan `python -m app.eval.run`.

Ditambah dua bagian yang menjawab rubrik secara langsung:

- **Kontrak** — tautan ke `docs/ARCHITECTURE.md` §4 dan penjelasan mekanisme
  berkas emas kembar.
- **Penggunaan AI secara bertanggung jawab** — §9 dokumen ini diringkas menjadi
  tiga paragraf, dengan nama berkas ujinya disebutkan. Ini menjawab Ketentuan
  Peserta butir 7 dengan bukti yang bisa dijalankan juri sendiri.

`docs/MODEL_CARD.md` memuat, dan tidak lebih dari:

| Bagian | Isi |
| --- | --- |
| Apa yang sistem ini lakukan | menyusun rencana tanam; ia **bukan** peramal harga dan **bukan** penjamin hasil |
| Masukan | tiga-titik tonase dan jendela panen dari model agronomi Go, bukan pengukuran lapangan |
| Metode | scalarisasi berbobot, CP-SAT, Monte Carlo segitiga |
| Hasil evaluasi | tabel §10.2 dengan angka nyata |
| Keterbatasan | dua butir §10.4, tertulis lengkap |
| Yang tidak boleh diklaim | "akurasi X%", "meningkatkan pendapatan petani sebesar Y" — tidak satu pun diuji lapangan |

Baris terakhir itu yang paling berharga di seluruh model card. Tim yang tahu apa
yang tidak boleh mereka klaim adalah tim yang angkanya bisa dipercaya untuk
hal-hal yang mereka klaim.

---

## 13. Urutan kerja

### Fase 1 — hari ini, 5–6 September (target ~4 jam)

Tujuan tunggal: **repo ini ada, jalan, dan lulus uji** saat pengumpulan.
Kualitas solver belum penting; keberadaan dan kebenaran kontrak yang penting.

- [ ] **1.1** `pyproject.toml`, `.gitignore`, `.env.example`, kerangka folder
- [ ] **1.2** `app/contracts/v1.py` lengkap
- [ ] **1.3** Salin `propose_request.golden.json` dan `propose_response.golden.json`
      dari repo Go ke `tests/fixtures/`. **Kalau belum ada, tulis dari
      `ARSITEKTUR_SISTEM_TERRION.md` §4.1/§4.2 dan kirimkan ke sisi Go.**
- [ ] **1.4** `tests/test_contract_golden.py` — berkas emas terurai, field terisi
- [ ] **1.5** `tests/test_no_personal_data.py` — tiga uji §9
- [ ] **1.6** `app/problem.py` — aritmetika minggu, `week_share`
- [ ] **1.7** `app/solver/{metrics,objectives,greedy}.py` + `solve_all`,
      **tanpa CP-SAT**
- [ ] **1.8** `app/risk/montecarlo.py`
- [ ] **1.9** `app/agent/{facts,guard,providers,explain}.py` dengan **hanya**
      penyedia `template`
- [ ] **1.10** `app/{config,security,logging,main}.py`
- [ ] **1.11** `tests/{test_endpoint,test_solver_determinism,test_guard}.py`
- [ ] **1.12** `pytest` hijau; `curl` lokal dengan berkas emas mengembalikan tiga
      rencana
- [ ] **1.13** `Dockerfile`, `fly.toml`, `fly deploy`
- [ ] **1.14** `README.md` lima bagian + tabel dependensi + bagian AI bertanggung
      jawab
- [ ] **1.15** Kabari sisi Go: URL dan token, supaya `AI_SERVICE_URL` bisa diisi

Gerbang Fase 1: `curl` ke `https://terrion-ai.fly.dev/v1/plan/propose` dengan
berkas emas mengembalikan tiga rencana valid dalam < 2 detik, **dan** mematikan
mesinnya (`fly scale count 0`) tidak menghasilkan satu pun galat di Terrion.

Butir 1.13 boleh gagal tanpa konsekuensi. Butir 1.1–1.12 dan 1.14 yang dinilai.

### Fase 2 — 7–18 September, untuk babak final

- [ ] **2.1** `app/solver/cpsat.py` + jalur cadangan `ImportError`
- [ ] **2.2** `tests/test_solver_quality.py` — CP-SAT ≥ greedy pada setiap
      objektif di fixture; kalau tidak, itu temuan yang dilaporkan
- [ ] **2.3** `app/eval/{baselines,run,report}.py` + fixture `subang_mt1.json`
      berukuran nyata (≥ 40 lahan)
- [ ] **2.4** Jalankan evaluasi, isi tabel §10.2 dengan angka nyata
- [ ] **2.5** Penyedia `openrouter`, ukur tingkat penolakan penjaga **dan latensi
      p95**, catat keduanya di model card
- [ ] **2.6** `docs/MODEL_CARD.md` lengkap
- [ ] **2.7** Faktor pergeseran musim berkorelasi di Monte Carlo (§10.4 butir 2)
- [ ] **2.8** Salin ADR dan `ARCHITECTURE.md` ke `docs/`
- [ ] **2.9** Latihan demo: matikan layanan di tengah demo, tunjukkan degradasinya
      sebagai fitur

Butir 2.9 layak dilatih sungguhan. Mendemonstrasikan sistem yang tetap bekerja
saat sebuah komponen dimatikan di depan mata juri jauh lebih meyakinkan daripada
slide mana pun yang mengklaim ketangguhan.

---

## 14. Yang tidak dikerjakan, dan alasannya

| Tidak dibangun | Alasan |
| --- | --- |
| Melatih model hasil panen di Python | Model ada di Go dan sudah terkalibrasi terhadap panen yang benar-benar tercatat. Dua model untuk satu besaran berarti dua jawaban dan tidak ada cara memilih. Slot `observations` di kontrak menunggu kalau ini berubah. |
| Prakiraan harga | Panel harga saat ini sintetis (§10.4). Meramal deret waktu sintetis adalah meramal fungsi sinus, dan menyebutnya AI adalah kebohongan. |
| Penyetelan hiperparameter otomatis | Ada tiga bobot per objektif, sembilan angka total. Menyetelnya terhadap fixture berjumlah puluhan lahan akan mencocokkan derau. Bobot ditetapkan dari makna, dan maknanya dituliskan. |
| Deteksi hama dari citra | Tidak ada data citra dan tidak ada di lingkup fitur. |
| Basis data vektor / RAG | Tidak ada korpus yang perlu diambil. Narasi bekerja atas fakta terhitung, bukan atas dokumen. |
| Fine-tuning | Untuk menghasilkan satu paragraf berbahasa Indonesia dari blok fakta terstruktur, prompt sudah cukup, dan hasilnya bisa diperiksa mekanis. |
| Streaming respons | Panggilannya server-ke-server dengan anggaran 3,5 detik. Streaming hanya menambah kerumitan pada penjaga numerik, yang butuh teks lengkap. |
| Autentikasi selain bearer token | Layanan ini punya tepat satu klien dan tidak punya konsep pengguna. OAuth di sini adalah upacara. |

Setiap baris di tabel ini adalah pekerjaan yang bisa dilakukan dan sengaja tidak
dilakukan. Menyebutkannya adalah bagian dari rencana, bukan kekurangannya:
proyek yang tahu batas lingkupnya menyelesaikan lingkup itu dengan baik.
