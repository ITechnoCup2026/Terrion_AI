"""Orkestrasi narasi: templat lebih dulu, model bahasa hanya boleh menggantikan."""

import asyncio

import httpx

from app.agent.facts import Facts
from app.agent.guard import ungrounded_numbers
from app.agent.providers import get_provider, template_narrative
from app.config import settings
from app.contracts.v1 import PlanResult
from app.logging import logger
from app.problem import Problem


async def narrate_all(
    plans: list[PlanResult], problem: Problem
) -> tuple[list[PlanResult], list[str]]:
    """Beri setiap rencana sebuah narasi, dan catat setiap penurunan mutu."""
    provider = get_provider(settings.llm_provider)
    degraded: list[str] = []
    out: list[PlanResult] = []

    for plan in plans:
        facts = Facts.from_plan(plan, problem)
        text, source = template_narrative(facts), "template"

        if provider.is_remote:
            try:
                candidate = await asyncio.wait_for(
                    provider.narrate(facts), timeout=settings.llm_timeout_ms / 1000
                )
                stray = ungrounded_numbers(candidate, facts.allowed_numbers())
                if not stray:
                    text, source = candidate, "llm"
                else:
                    degraded.append(f"{plan.objective}:ungrounded_numbers")
                    logger.warning(
                        "narasi_ditolak", objective=plan.objective, stray=stray[:5]
                    )
            except (TimeoutError, httpx.HTTPError) as exc:
                degraded.append(f"{plan.objective}:llm_unavailable")
                logger.warning("llm_gagal", objective=plan.objective, error=str(exc))

        out.append(plan.model_copy(update={"narrative": text, "narrative_source": source}))

    return out, degraded
