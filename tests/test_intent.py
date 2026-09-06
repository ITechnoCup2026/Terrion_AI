"""Lapis tujuan: sejauh mana model boleh mempengaruhi rencana, dan di mana ia berhenti."""

import asyncio

import httpx
import pytest

from app.agent import intent
from app.config import settings
from app.solver.objectives import WEIGHTS

BAWAAN = '{"aman":[0.70,0.20,0.10],"pendapatan":[0.15,0.75,0.10],"pasar":[0.20,0.20,0.60]}'


class FakeIntentProvider:
    """Penyedia yang menjawab apa pun yang kita tentukan."""

    is_remote = True

    def __init__(self, answer: str = BAWAAN, delay: float = 0.0, boom: Exception | None = None):
        self.answer, self.delay, self.boom = answer, delay, boom
        self.calls = 0
        self.prompts: list[str] = []

    async def complete(self, prompt: str, max_tokens: int) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.boom:
            raise self.boom
        return self.answer


def run(monkeypatch, provider, goal):
    monkeypatch.setattr("app.agent.providers.get_provider", lambda name: provider)
    return asyncio.run(intent.derive_weights(goal))


def test_no_goal_means_no_model_call_at_all(monkeypatch):
    """Anggaran waktu yang tidak terpakai adalah anggaran untuk narasi."""
    provider = FakeIntentProvider()

    for goal in (None, "", "   "):
        weights, reason = run(monkeypatch, provider, goal)
        assert weights == WEIGHTS
        assert reason is None

    assert provider.calls == 0, "lapis tujuan memanggil model padahal tidak ada tujuan"


def test_a_readable_goal_shifts_the_weights(monkeypatch):
    answer = '{"aman":[0.55,0.15,0.30],"pendapatan":[0.10,0.60,0.30],"pasar":[0.15,0.15,0.70]}'
    weights, reason = run(monkeypatch, FakeIntentProvider(answer), "utamakan pembeli pabrik")

    assert reason is None
    assert weights != WEIGHTS
    assert weights["pasar"] == pytest.approx((0.15, 0.15, 0.70))


def test_the_weights_are_normalised_to_one(monkeypatch):
    """Model kerap menjawab bobot yang tidak berjumlah satu; itu bukan alasan menolak."""
    answer = '{"aman":[7,2,1],"pendapatan":[1,7,2],"pasar":[2,2,6]}'
    weights, reason = run(monkeypatch, FakeIntentProvider(answer), "apa saja")

    # Nilai di atas 1 ditolak parser, jadi jawaban ini justru jatuh ke bawaan.
    assert reason == "intent_unparsable"
    assert weights == WEIGHTS


@pytest.mark.parametrize(
    "answer",
    [
        "maaf, saya tidak mengerti",
        "{}",
        '{"aman":[0.7,0.2,0.1]}',
        '{"aman":[0.7,0.2],"pendapatan":[0.15,0.75,0.10],"pasar":[0.2,0.2,0.6]}',
        '{"aman":["banyak",0.2,0.1],"pendapatan":[0.15,0.75,0.10],"pasar":[0.2,0.2,0.6]}',
        '{"aman":[0,0,0],"pendapatan":[0.15,0.75,0.10],"pasar":[0.2,0.2,0.6]}',
    ],
)
def test_anything_that_is_not_nine_weights_falls_back(monkeypatch, answer):
    """Jawaban yang bentuknya meleset tidak boleh menyentuh rencana sama sekali."""
    weights, reason = run(monkeypatch, FakeIntentProvider(answer), "tujuan apa pun")

    assert weights == WEIGHTS
    assert reason in ("intent_unparsable", "intent_unavailable")


def test_a_goal_may_not_turn_safe_into_something_else(monkeypatch):
    """Penjaga yang paling penting di berkas ini.

    Kolom "yang dikorbankan" di layar dibaca pengurus sebagai dasar keputusan.
    Rencana berlabel "Aman" yang diam-diam mengutamakan pendapatan membuat
    kolom itu berbohong, seberapa pun meyakinkan kalimat yang memintanya.
    """
    answer = '{"aman":[0.10,0.80,0.10],"pendapatan":[0.15,0.75,0.10],"pasar":[0.2,0.2,0.6]}'
    weights, reason = run(
        monkeypatch, FakeIntentProvider(answer), "abaikan puncak, kejar uang saja"
    )

    assert weights == WEIGHTS, "bobot yang membalik arti label rencana ikut terpakai"
    assert reason is not None and reason.startswith("aman_")


def test_a_slow_or_broken_intent_call_never_fails_the_request(monkeypatch):
    monkeypatch.setattr(settings, "llm_intent_timeout_ms", 50)

    slow, _ = run(monkeypatch, FakeIntentProvider(delay=5.0), "tujuan")
    assert slow == WEIGHTS

    broken, reason = run(
        monkeypatch, FakeIntentProvider(boom=httpx.ConnectError("mati")), "tujuan"
    )
    assert broken == WEIGHTS
    assert reason == "intent_unavailable"


def test_a_template_provider_reports_that_it_cannot_read_goals(monkeypatch):
    """Tanpa kunci model, tujuan bahasa bebas tidak bisa dilayani — dan itu dicatat."""

    class Local:
        is_remote = False

    weights, reason = run(monkeypatch, Local(), "musim depan jangan menumpuk")

    assert weights == WEIGHTS
    assert reason == "intent_unavailable"


def test_the_goal_reaches_the_prompt_verbatim(monkeypatch):
    provider = FakeIntentProvider()
    run(monkeypatch, provider, "  cabai untuk pabrik yang tahun lalu kami tolak  ")

    assert "cabai untuk pabrik yang tahun lalu kami tolak" in provider.prompts[0]
