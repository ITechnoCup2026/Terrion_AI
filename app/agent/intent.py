"""Lapis tujuan: kalimat pengurus menjadi bobot, dan tidak pernah lebih dari itu.

Ini satu-satunya tempat model bahasa boleh mempengaruhi ISI rencana, bukan
sekadar kata-katanya — jadi batas kewenangannya ditarik ketat di sini.

**Yang boleh dihasilkan model:** tiga bilangan per objektif, masing-masing
antara 0 dan 1. Itu saja.

**Yang tidak boleh:** angka apa pun yang sampai ke pengurus. Bobot bukan
angka yang dibaca siapa pun; ia hanya menggeser apa yang dicari solver, dan
setiap tonase, rupiah, dan tanggal tetap dihitung solver deterministik. Tidak
ada jalur bagi halusinasi model untuk masuk ke formulir RDKK — itu Ketentuan
Peserta no. 7, dan bentuk penegakannya adalah berkas ini.

**Kalau apa pun meleset**, bobot bawaan yang dipakai dan alasannya dicatat.
Tujuan yang tidak terbaca berarti rencana yang lebih kaku, bukan permintaan
yang gagal.
"""

import asyncio
import json
import re

import httpx

from app.config import settings
from app.logging import logger
from app.solver.objectives import WEIGHTS, Weights

OBJECTIVES = ("aman", "pendapatan", "pasar")

# Bobot yang tidak boleh digeser terlalu jauh dari maksud labelnya. Rencana
# berlabel "Aman" yang berhenti mengutamakan puncak rendah membuat label di
# layar berbohong, seberapa pun meyakinkan kalimat yang meminta.
FLOOR = 0.35

PROMPT = """Kamu menerjemahkan tujuan pengurus koperasi tani menjadi bobot optimasi.

TUJUAN PENGURUS:
{goal}

Ada tiga rencana yang selalu dihasilkan, masing-masing dengan tiga bobot:
- "aman"       : bobot (ratakan puncak panen, kejar pendapatan, penuhi permintaan)
- "pendapatan" : bobot yang sama urutannya
- "pasar"      : bobot yang sama urutannya

ATURAN
- Jawab HANYA satu objek JSON, tanpa penjelasan, tanpa pagar kode.
- Bentuknya persis: {{"aman":[a,b,c],"pendapatan":[a,b,c],"pasar":[a,b,c]}}
- Setiap bilangan antara 0 dan 1. Tiap tiga bilangan berjumlah 1.
- Rencana "aman" harus tetap paling mementingkan puncak yang rata, "pendapatan"
  tetap paling mementingkan pendapatan, "pasar" tetap paling mementingkan
  permintaan pembeli. Geser penekanannya, jangan tukar artinya.
- Jangan menulis angka apa pun selain kesembilan bobot itu.

Bobot bawaan, kalau tujuannya tidak mengubah apa-apa:
{{"aman":[0.70,0.20,0.10],"pendapatan":[0.15,0.75,0.10],"pasar":[0.20,0.20,0.60]}}
"""

# Indeks bobot yang wajib tetap dominan untuk tiap objektif.
DOMINANT = {"aman": 0, "pendapatan": 1, "pasar": 2}

JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse(text: str) -> Weights | None:
    """Baca bobot dari jawaban model, atau None kalau bentuknya tidak sesuai."""
    match = JSON_OBJECT.search(text or "")
    if not match:
        return None

    try:
        raw = json.loads(match.group())
    except json.JSONDecodeError:
        return None

    if not isinstance(raw, dict) or set(raw) != set(OBJECTIVES):
        return None

    weights: Weights = {}
    for objective in OBJECTIVES:
        row = raw[objective]
        if not isinstance(row, list) or len(row) != 3:
            return None
        if not all(isinstance(v, int | float) and 0 <= v <= 1 for v in row):
            return None
        weights[objective] = (float(row[0]), float(row[1]), float(row[2]))
    return weights


def _normalise(weights: Weights) -> Weights | None:
    """Jadikan tiap baris berjumlah satu, dan tolak yang seluruhnya nol."""
    fixed: Weights = {}
    for objective, row in weights.items():
        total = sum(row)
        if total < 1e-9:
            return None
        fixed[objective] = tuple(value / total for value in row)
    return fixed


def rejection_reason(weights: Weights) -> str | None:
    """Alasan menolak bobot usulan model, atau None kalau ia layak dipakai.

    Satu-satunya pemeriksaan yang benar-benar penting: label rencana harus
    tetap berarti. Bobot yang membuat "aman" mengutamakan pendapatan akan
    menampilkan kolom "yang dikorbankan" yang terbalik, dan pengurus mengambil
    keputusan dari kolom itu.
    """
    for objective, index in DOMINANT.items():
        row = weights[objective]
        if row[index] < FLOOR:
            return f"{objective}_kehilangan_maknanya"
        if row[index] < max(row) - 1e-9:
            return f"{objective}_bukan_lagi_tentang_{('puncak', 'pendapatan', 'pasar')[index]}"
    return None


async def _ask(provider, goal: str) -> str:
    """Satu panggilan model, dengan anggaran waktunya sendiri."""
    response = await asyncio.wait_for(
        provider.complete(PROMPT.format(goal=goal), settings.llm_intent_max_tokens),
        timeout=settings.llm_intent_timeout_ms / 1000,
    )
    return response


async def derive_weights(goal: str | None) -> tuple[Weights, str | None]:
    """Terjemahkan tujuan bahasa bebas menjadi bobot; bawaan bila gagal.

    Mengembalikan (bobot, alasan_penurunan). Alasan yang bukan None berarti
    bobot bawaan yang dipakai, dan ia dilaporkan lewat `degraded` supaya
    pengurus tahu kalimatnya tidak terbaca — bukan disembunyikan.
    """
    from app.agent.providers import get_provider

    if not goal or not goal.strip():
        return WEIGHTS, None

    provider = get_provider(settings.llm_provider)
    if not provider.is_remote:
        return WEIGHTS, "intent_unavailable"

    try:
        text = await _ask(provider, goal.strip())
    except (TimeoutError, httpx.HTTPError) as exc:
        logger.warning("tujuan_gagal", error=repr(exc))
        return WEIGHTS, "intent_unavailable"

    parsed = _parse(text)
    if parsed is None:
        logger.warning("tujuan_tidak_terbaca", panjang=len(text or ""))
        return WEIGHTS, "intent_unparsable"

    normalised = _normalise(parsed)
    if normalised is None:
        return WEIGHTS, "intent_unparsable"

    reason = rejection_reason(normalised)
    if reason:
        logger.warning("tujuan_ditolak", reason=reason)
        return WEIGHTS, reason

    logger.info("tujuan_terbaca", weights=normalised)
    return normalised, None
