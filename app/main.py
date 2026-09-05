"""Aplikasi FastAPI: satu endpoint kerja, dua endpoint operasional."""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.explain import narrate_all
from app.agent.providers import aclose_client, get_provider, warm_client
from app.config import settings
from app.contracts.v1 import (
    CONTRACT_MAJOR,
    CONTRACT_VERSION,
    Diagnostics,
    ProposeRequest,
    ProposeResponse,
)
from app.logging import bind_request, configure_logging, logger
from app.problem import Problem
from app.risk.montecarlo import peak_quantiles
from app.security import require_token
from app.solver import cpsat_available, solve_all
from app.solver.metrics import plan_result

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Panaskan koneksi ke penyedia lebih dulu, lalu tutup rapi di akhir.

    Handshake TLS pertama sebuah proses terukur 1,4 detik. Kalau ia dibayar
    di dalam permintaan pertama, ia dibayar dari anggaran narasi yang
    seluruhnya hanya 2,8 detik — dan itulah yang terlihat di log produksi:
    ketiga narasi gagal berbarengan tepat pada permintaan pertama setelah
    deploy, lalu permintaan berikutnya baik-baik saja. Dipanaskan di sini,
    handshake itu dibayar ketika belum ada yang menunggu.

    Sebagai tugas latar, bukan di jalur startup: penyedia yang sedang
    bermasalah tidak boleh menahan proses ini dari melayani /health.

    Klien yang sama dipakai seluruh proses dan harus ditutup rapi saat
    berhenti, kalau tidak koneksi yang menggantung membuat SIGTERM saat
    redeploy terasa jauh lebih lama dari seharusnya.
    """
    warming = None
    if get_provider(settings.llm_provider).is_remote:
        warming = asyncio.create_task(warm_client())

    yield

    if warming is not None:
        warming.cancel()
    await aclose_client()


app = FastAPI(title="Terrion AI", version="1.0.0", docs_url="/docs", lifespan=lifespan)


def envelope(code: str, message: str) -> dict:
    """Amplop galat, dan hanya ini bentuknya."""
    return {"error": {"code": code, "message": message}}


@app.exception_handler(RequestValidationError)
async def on_invalid_request(request: Request, exc: RequestValidationError):
    """Petakan kegagalan validasi ke kode galat yang dijanjikan kontrak."""
    too_large = any(error["type"] == "too_long" for error in exc.errors())
    if too_large:
        return JSONResponse(
            status_code=422,
            content=envelope("problem_too_large", "batas ukuran terlampaui"),
        )
    return JSONResponse(
        status_code=400,
        content=envelope("malformed_request", str(exc.errors()[:3])),
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: proses hidup."""
    return {"status": "ok", "service": "terrion-ai"}


@app.get("/ready")
async def ready() -> dict[str, object]:
    """Readiness: solver siap dan konfigurasi lengkap."""
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "cpsat": cpsat_available(),
        "llm_provider": settings.llm_provider,
    }


@app.post(
    "/v1/plan/propose",
    response_model=ProposeResponse,
    dependencies=[Depends(require_token)],
)
async def propose(payload: ProposeRequest, request: Request):
    """Selesaikan soal perencanaan dan kembalikan satu rencana per objektif."""
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or payload.request_id or str(uuid.uuid4())
    bind_request(request_id)

    if not payload.contract_version.startswith(f"{CONTRACT_MAJOR}."):
        return JSONResponse(
            status_code=409,
            content=envelope(
                "contract_version_unsupported",
                f"layanan berbicara {CONTRACT_VERSION}, permintaan {payload.contract_version}",
            ),
        )

    problem = Problem.from_request(payload)
    solutions, solver_name, status_name, evaluations = solve_all(problem, payload.seed)

    plans = []
    for objective in problem.objectives:
        chosen = problem.select(solutions.get(objective, []))
        p50, p90 = peak_quantiles(chosen, problem, settings.monte_carlo_draws, payload.seed)
        plans.append(plan_result(objective, chosen, problem, p50, p90))

    plans, degraded = await narrate_all(plans, problem)

    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info(
        "propose",
        candidates=len(payload.candidates),
        solver=solver_name,
        elapsed_ms=elapsed,
        degraded=degraded,
    )

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
