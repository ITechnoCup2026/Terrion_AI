"""Dua cara menulis narasi: templat lokal, atau model bahasa lewat OpenRouter."""

from pathlib import Path

import httpx

from app.agent.facts import Facts, format_number
from app.config import settings

PROMPT_PATH = Path(__file__).parent / "prompts" / "narrate_id.txt"

OPENING = {
    "aman": "Rencana ini disusun agar panen tidak menumpuk di satu minggu.",
    "pendapatan": "Rencana ini disusun untuk mengejar nilai panen tertinggi.",
    "pasar": "Rencana ini disusun untuk memenuhi permintaan pembeli yang sudah ada.",
}


def render_prompt(facts: Facts) -> str:
    """Susun prompt dari blok fakta dan tujuan rencana."""
    return PROMPT_PATH.read_text(encoding="utf-8").format(
        facts=facts.block(), objective=facts.objective
    )


def template_narrative(facts: Facts) -> str:
    """Rangkai kalimat Indonesia dari fakta, tanpa jaringan dan tanpa kunci.

    Setiap angka di sini berasal dari blok fakta, sehingga narasi templat
    selalu lolos penjaga numerik.
    """
    parts = [
        OPENING[facts.objective],
        (
            f"Sebanyak {format_number(facts.plots)} lahan ditanami dengan "
            f"{format_number(facts.varieties)} varietas, sehingga panen tersebar di "
            f"{format_number(facts.harvest_weeks)} minggu, dari pekan "
            f"{facts.first_harvest_week} sampai pekan {facts.last_harvest_week}."
        ),
        (
            f"Dari perkiraan total {format_number(facts.total_tonnes)} ton, puncak "
            f"panen mingguan berada di sekitar {format_number(facts.peak_p50)} ton, "
            f"dan sembilan dari sepuluh musim tetap di bawah "
            f"{format_number(facts.peak_p90)} ton."
        ),
    ]

    if facts.capacity is not None:
        parts.append(
            f"Kapasitas tampung koperasi adalah {format_number(facts.capacity)} "
            f"ton per minggu."
        )
    if facts.demand_covered_kg:
        parts.append(
            f"Rencana ini menutup {format_number(facts.demand_covered_kg)} kg "
            f"permintaan pembeli."
        )

    parts.append("Angka di atas adalah proyeksi, bukan kepastian.")
    return " ".join(parts)


class Template:
    """Penyedia bawaan: deterministik, tanpa jaringan, selalu tersedia."""

    is_remote = False

    async def narrate(self, facts: Facts) -> str:
        """Kembalikan kalimat templat."""
        return template_narrative(facts)


class OpenRouter:
    """Penyedia jarak jauh, opsional, dengan daftar model cadangan bawaan."""

    is_remote = True

    async def narrate(self, facts: Facts) -> str:
        """Minta satu paragraf ke model bahasa; keluarannya belum dipercaya."""
        payload = {
            "model": settings.llm_model,
            "temperature": 0.2,
            "seed": facts.seed,
            "max_tokens": 220,
            "messages": [{"role": "user", "content": render_prompt(facts)}],
        }
        fallbacks = [m.strip() for m in settings.llm_fallback_models.split(",") if m.strip()]
        if fallbacks:
            payload["models"] = [settings.llm_model, *fallbacks]

        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "HTTP-Referer": "https://github.com/ITechnoCup2026",
            "X-Title": "Terrion",
        }

        async with httpx.AsyncClient(base_url=settings.llm_base_url) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()


def get_provider(name: str):
    """Pilih penyedia menurut konfigurasi; apa pun selain openrouter berarti templat."""
    if name == "openrouter" and settings.llm_api_key:
        return OpenRouter()
    return Template()
