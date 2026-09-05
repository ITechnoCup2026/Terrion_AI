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


async def _remote_draft(provider, facts: Facts) -> tuple[str | None, str | None]:
    """Satu narasi model: teksnya kalau layak, atau alasan kenapa ditolak.

    Tidak pernah melempar. Setiap jalur kegagalan menjadi satu kode alasan,
    karena narasi yang gagal bukan permintaan yang gagal — templatnya sudah
    benar dan sudah siap dipakai.
    """
    try:
        draft = await asyncio.wait_for(
            provider.narrate(facts), timeout=settings.llm_timeout_ms / 1000
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
    plans: list[PlanResult], problem: Problem
) -> tuple[list[PlanResult], list[str]]:
    """Beri setiap rencana sebuah narasi, dan catat setiap penurunan mutu."""
    provider = get_provider(settings.llm_provider)
    facts = [Facts.from_plan(plan, problem) for plan in plans]
    texts = [template_narrative(f) for f in facts]
    sources = ["template"] * len(plans)
    degraded: list[str] = []

    if provider.is_remote:
        # Serentak, bukan berurutan. Tiga panggilan berurutan dengan anggaran
        # 2 detik masing-masing berarti 6 detik pada kasus terburuk, sementara
        # sisi Go menutup panggilan pada 3,5 detik — jadi bentuk berurutan
        # menjamin fallback justru pada saat model paling dibutuhkan. Serentak,
        # kasus terburuknya satu anggaran, bukan tiga.
        results = await asyncio.gather(*(_remote_draft(provider, f) for f in facts))
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
