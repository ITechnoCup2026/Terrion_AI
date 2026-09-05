"""Apa yang terjadi pada narasi model sebelum ia boleh menggantikan templat."""

import asyncio
import time

import pytest

from app.agent import explain
from app.agent.facts import Facts
from app.agent.providers import Draft, template_narrative
from app.contracts.v1 import PlanResult


class FakeRemote:
    """Penyedia jarak jauh palsu yang mengembalikan draf yang sudah ditentukan."""

    is_remote = True

    def __init__(self, draft: Draft | None = None, delay: float = 0.0, maker=None):
        self.draft, self.delay, self.maker = draft, delay, maker
        self.calls = 0

    async def narrate(self, facts: Facts) -> Draft:
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.maker(facts) if self.maker else self.draft


@pytest.fixture
def plans(golden_response):
    return [PlanResult.model_validate(p) for p in golden_response["plans"]]


def run(monkeypatch, provider, plans, problem):
    monkeypatch.setattr(explain, "get_provider", lambda name: provider)
    return asyncio.run(explain.narrate_all(plans, problem))


def test_an_empty_answer_never_replaces_the_template(monkeypatch, plans, problem):
    """Regresi: teks kosong tidak memuat angka liar, jadi dulu ia LOLOS penjaga.

    Model reasoning yang menghabiskan seluruh anggaran token untuk berpikir
    mengembalikan konten kosong dengan finish_reason "stop". Sebelum
    rejection_reason ada, narasi benar diganti string kosong berlabel "llm".
    """
    out, degraded = run(monkeypatch, FakeRemote(Draft("")), plans, problem)

    assert [p.narrative_source for p in out] == ["template"] * len(plans)
    assert all(p.narrative for p in out)
    assert degraded == [f"{p.objective}:narrative_too_short" for p in plans]


def test_a_truncated_answer_is_rejected_even_when_its_numbers_are_right(
    monkeypatch, plans, problem
):
    """finish_reason "length" tidak terbaca dari teksnya, jadi ia harus dibawa."""
    good = template_narrative(Facts.from_plan(plans[0], problem))
    out, degraded = run(monkeypatch, FakeRemote(Draft(good, truncated=True)), plans, problem)

    assert [p.narrative_source for p in out] == ["template"] * len(plans)
    assert degraded == [f"{p.objective}:truncated" for p in plans]


def test_a_grounded_answer_does_replace_the_template(monkeypatch, plans, problem):
    # Tiap rencana punya daftar angka sahnya sendiri, jadi teksnya dibuat
    # per-fakta — bukan satu teks yang sama untuk ketiganya.
    def maker(f):
        return Draft("Menurut model bahasa: " + template_narrative(f))

    out, degraded = run(monkeypatch, FakeRemote(maker=maker), plans, problem)

    assert degraded == []
    assert [p.narrative_source for p in out] == ["llm"] * len(plans)
    assert all(p.narrative.startswith("Menurut model bahasa:") for p in out)


def test_an_invented_number_is_rejected(monkeypatch, plans, problem):
    def maker(f):
        return Draft(template_narrative(f) + " Keuntungannya naik 173 persen.")

    out, degraded = run(monkeypatch, FakeRemote(maker=maker), plans, problem)

    assert [p.narrative_source for p in out] == ["template"] * len(plans)
    assert degraded == [f"{p.objective}:ungrounded_numbers" for p in plans]


def test_a_provider_that_hangs_costs_one_budget_not_three(monkeypatch, plans, problem):
    """Bukti bahwa ketiga narasi dipanggil serentak.

    Berurutan, tiga rencana × 2 detik = 6 detik, sementara sisi Go menutup
    panggilan pada 3,5 detik. Serentak, kasus terburuknya satu anggaran.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "llm_timeout_ms", 300)
    provider = FakeRemote(Draft("tidak akan pernah sampai"), delay=5.0)

    started = time.perf_counter()
    out, degraded = run(monkeypatch, provider, plans, problem)
    elapsed = time.perf_counter() - started

    assert provider.calls == len(plans)
    assert degraded == [f"{p.objective}:llm_unavailable" for p in plans]
    assert [p.narrative_source for p in out] == ["template"] * len(plans)
    assert elapsed < 0.3 * len(plans), (
        f"{elapsed:.2f}s untuk {len(plans)} rencana — terlihat berurutan, bukan serentak"
    )


def test_the_plain_payload_carries_nothing_a_gateway_can_reject(plans, problem):
    """Regresi terhadap 400 yang benar-benar terjadi.

    Sumopod berjalan di atas LiteLLM, yang meneruskan parameter tak dikenal ke
    penyedia hulu. Diuji langsung ke Sumopod: `models` dan `reasoning`
    masing-masing dijawab 400 "Unrecognized request argument supplied",
    sementara payload polos dijawab 200. Jadi apa pun yang khas satu penyedia
    tidak boleh menetes ke kelas induknya.
    """
    from app.agent.providers import OpenAICompatible

    facts = Facts.from_plan(plans[0], problem)
    provider = OpenAICompatible()

    assert set(provider.payload(facts)) == {
        "model", "temperature", "seed", "max_tokens", "messages",
    }
    assert set(provider.headers()) == {"Authorization"}


def test_openrouter_keeps_its_own_parameters_to_itself(monkeypatch, plans, problem):
    from app.agent.providers import OpenRouter
    from app.config import settings

    monkeypatch.setattr(settings, "llm_model", "model-utama")
    monkeypatch.setattr(settings, "llm_fallback_models", "cadangan-a, cadangan-b")
    body = OpenRouter().payload(Facts.from_plan(plans[0], problem))

    assert body["reasoning"] == {"enabled": False}
    assert body["models"] == ["model-utama", "cadangan-a", "cadangan-b"]
    assert "HTTP-Referer" in OpenRouter().headers()


def test_the_provider_name_decides_the_dialect(monkeypatch):
    from app.agent import providers
    from app.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "kunci-palsu")
    assert type(providers.get_provider("sumopod")) is providers.OpenAICompatible
    assert type(providers.get_provider("openrouter")) is providers.OpenRouter
    assert type(providers.get_provider("entah-apa")) is providers.Template

    monkeypatch.setattr(settings, "llm_api_key", "")
    assert type(providers.get_provider("sumopod")) is providers.Template
