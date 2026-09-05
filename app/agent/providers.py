"""Dua cara menulis narasi: templat lokal, atau model bahasa lewat OpenRouter."""

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.agent.facts import Facts, format_number
from app.config import settings

PROMPT_PATH = Path(__file__).parent / "prompts" / "narrate_id.txt"


@dataclass(frozen=True)
class Draft:
    """Narasi mentah beserta satu hal yang tidak terbaca dari teksnya.

    `truncated` datang dari finish_reason, bukan dari isi teks. Jawaban
    yang habis di tengah kalimat tetap tampak wajar dan tetap bisa lolos
    pemeriksaan angka, jadi satu-satunya cara mengetahuinya adalah
    bertanya pada penyedia.
    """

    text: str
    truncated: bool = False


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

    async def narrate(self, facts: Facts) -> Draft:
        """Kembalikan kalimat templat; ia tidak pernah terpotong."""
        return Draft(template_narrative(facts))


_client: httpx.AsyncClient | None = None


def shared_client() -> httpx.AsyncClient:
    """Satu klien HTTP untuk seluruh proses, dan ini bukan penghematan objek.

    Handshake TLS ke penyedia diukur memakan 1-3 detik — pada benchmark,
    panggilan pertama ke setiap model selalu 2-3x lebih lambat dari
    berikutnya. Klien baru per panggilan berarti setiap narasi membayar
    handshake itu lagi, tiga kali per permintaan, di dalam anggaran yang
    seluruhnya hanya 2,8 detik. Dengan satu klien, hanya permintaan pertama
    setelah proses hidup yang membayarnya.
    """
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
    return _client


async def aclose_client() -> None:
    """Tutup klien bersama saat proses berhenti."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


class OpenAICompatible:
    """Penyedia mana pun yang berbicara skema /chat/completions milik OpenAI.

    Ini yang dipakai untuk Sumopod. Badan permintaannya sengaja polos: hanya
    field yang ada di spesifikasi OpenAI. Sumopod berjalan di atas LiteLLM,
    dan LiteLLM meneruskan parameter tak dikenal ke penyedia hulu, yang
    menolaknya dengan 400 "Unrecognized request argument supplied". Diuji
    langsung: `models` dan `reasoning` masing-masing 400, payload polos 200.
    """

    is_remote = True

    def payload(self, facts: Facts) -> dict:
        """Badan permintaan yang setiap penyedia skema OpenAI pasti terima."""
        return {
            "model": settings.llm_model,
            "temperature": 0.2,
            "seed": facts.seed,
            "max_tokens": settings.llm_max_tokens,
            "messages": [{"role": "user", "content": render_prompt(facts)}],
        }

    def headers(self) -> dict:
        """Kredensial saja; tidak ada penyedia yang menolak header ini."""
        return {"Authorization": f"Bearer {settings.llm_api_key}"}

    async def narrate(self, facts: Facts) -> Draft:
        """Minta satu paragraf ke model bahasa; keluarannya belum dipercaya."""
        response = await shared_client().post(
            settings.llm_base_url.rstrip("/") + "/chat/completions",
            json=self.payload(facts),
            headers=self.headers(),
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]
        return Draft(
            text=(choice["message"].get("content") or "").strip(),
            truncated=choice.get("finish_reason") == "length",
        )


class OpenRouter(OpenAICompatible):
    """OpenAI-compatible, plus tiga hal yang hanya OpenRouter yang mengerti.

    Ketiganya ditolak 400 oleh penyedia lain, jadi mereka tinggal di sini
    dan bukan di kelas induknya.
    """

    def payload(self, facts: Facts) -> dict:
        """Tambahkan daftar model cadangan dan pematian reasoning."""
        body = super().payload(facts)
        # Seluruh model :free di katalog OpenRouter adalah model reasoning dan
        # bawaannya berpikir sebelum menjawab. Tanpa baris ini minimax-m2.7
        # menghabiskan 207 dari 220 token untuk berpikir lalu mengembalikan
        # konten KOSONG. "enabled": False, bukan "exclude": True — yang kedua
        # hanya menyembunyikan token reasoning, tetap membakarnya.
        body["reasoning"] = {"enabled": False}

        fallbacks = [m.strip() for m in settings.llm_fallback_models.split(",") if m.strip()]
        if fallbacks:
            # Routing cadangan milik OpenRouter sendiri. Penyedia lain tidak
            # punya padanannya, dan mencoba ulang secara manual berarti
            # membayar anggaran waktu dua kali — jadi di luar OpenRouter,
            # LLM_FALLBACK_MODELS memang tidak dipakai.
            body["models"] = [settings.llm_model, *fallbacks]
        return body

    def headers(self) -> dict:
        """Atribusi yang diminta OpenRouter dari aplikasi pemanggil."""
        return super().headers() | {
            "HTTP-Referer": "https://github.com/ITechnoCup2026",
            "X-Title": "Terrion",
        }


REMOTE = {
    "openrouter": OpenRouter,
    "sumopod": OpenAICompatible,
    "openai": OpenAICompatible,
}


def get_provider(name: str):
    """Pilih penyedia menurut konfigurasi; tanpa kunci, selalu templat.

    Nama yang tidak dikenal jatuh ke templat dan bukan galat: layanan yang
    salah konfigurasi harus tetap menjawab dengan angka yang benar.
    """
    factory = REMOTE.get(name)
    if factory and settings.llm_api_key:
        return factory()
    return Template()
