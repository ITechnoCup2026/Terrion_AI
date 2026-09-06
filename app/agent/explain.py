"""Orkestrasi narasi: templat lebih dulu, model bahasa hanya boleh menggantikan."""

import asyncio

import httpx

from app.agent.facts import Facts
from app.agent.guard import rejection_reason
from app.agent.providers import get_provider, template_narrative
from app.config import settings
from app.contracts.v1 import PlanResult
from app.logging import logger
from app.problem import Problem

# Di bawah ini satu panggilan pasti gagal: waktu sampai token pertama saja
# terukur 720-900 ms, jadi memulainya hanya membuang sisa anggaran yang bisa
# dipakai menyerahkan respons tepat waktu.
MINIMUM_NARRATION_MS = 1000


async def _remote_draft(
    provider, facts: Facts, budget_ms: int
) -> tuple[str | None, str | None]:
    """Satu narasi model: teksnya kalau layak, atau alasan kenapa ditolak.

    Tidak pernah melempar. Setiap jalur kegagalan menjadi satu kode alasan,
    karena narasi yang gagal bukan permintaan yang gagal — templatnya sudah
    benar dan sudah siap dipakai.
    """
    try:
        draft = await asyncio.wait_for(
            provider.narrate(facts), timeout=budget_ms / 1000
        )
    except (TimeoutError, httpx.HTTPError) as exc:
        # repr, bukan str: str(TimeoutError()) adalah string kosong, dan log
        # yang berbunyi error="" tidak memberi tahu siapa pun apa pun.
        logger.warning("llm_gagal", objective=facts.objective, error=repr(exc))
        return None, "llm_unavailable"

    reason = rejection_reason(draft.text, facts.allowed_numbers(), draft.truncated)
    if reason:
        logger.warning(
            "narasi_ditolak",
            objective=facts.objective,
            reason=reason,
            panjang=len(draft.text),
        )
        return None, reason

    return draft.text, None


async def narrate_all(
    plans: list[PlanResult], problem: Problem, budget_ms: int | None = None
) -> tuple[list[PlanResult], list[str]]:
    """Beri setiap rencana sebuah narasi, dan catat setiap penurunan mutu.

    `budget_ms` adalah sisa waktu permintaan, bukan jatah tetap: lapis tujuan
    dan solver sudah memakai bagiannya lebih dulu. Sisa yang terlalu tipis
    untuk menghasilkan paragraf berarti templat dipakai tanpa sempat mencoba —
    lebih baik daripada memulai panggilan yang pasti dibatalkan sisi Go.
    """
    # Lantai hanya berlaku pada anggaran SISA. Anggaran yang disetel operator
    # lewat LLM_TIMEOUT_MS dihormati apa adanya, sekecil apa pun — yang ingin
    # dicegah adalah memulai panggilan ketika waktu permintaan sudah habis,
    # bukan menolak konfigurasi yang sengaja ketat.
    exhausted = budget_ms is not None and budget_ms < MINIMUM_NARRATION_MS
    budget = (
        settings.llm_timeout_ms
        if budget_ms is None
        else min(budget_ms, settings.llm_timeout_ms)
    )

    provider = get_provider(settings.llm_provider)
    facts = [Facts.from_plan(plan, problem) for plan in plans]
    texts = [template_narrative(f) for f in facts]
    sources = ["template"] * len(plans)
    degraded: list[str] = []

    if provider.is_remote and exhausted:
        # Anggaran habis sebelum narasi sempat dimulai. Dicatat, tidak
        # disembunyikan: pengurus berhak tahu paragrafnya templat.
        logger.warning("narasi_dilewati", sisa_ms=budget_ms)
        degraded.extend(f"{plan.objective}:budget_exhausted" for plan in plans)
    elif provider.is_remote:
        # Serentak, bukan berurutan. Tiga panggilan berurutan dengan anggaran
        # 2 detik masing-masing berarti 6 detik pada kasus terburuk, sementara
        # sisi Go menutup panggilan pada 3,5 detik — jadi bentuk berurutan
        # menjamin fallback justru pada saat model paling dibutuhkan. Serentak,
        # kasus terburuknya satu anggaran, bukan tiga.
        results = await asyncio.gather(
            *(_remote_draft(provider, f, budget) for f in facts)
        )
        for index, (text, reason) in enumerate(results):
            if reason:
                degraded.append(f"{plans[index].objective}:{reason}")
            else:
                texts[index], sources[index] = text, "llm"

    out = [
        plan.model_copy(update={"narrative": text, "narrative_source": source})
        for plan, text, source in zip(plans, texts, sources, strict=True)
    ]
    return out, degraded
