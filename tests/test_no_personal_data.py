import re
from copy import deepcopy

import pytest
from pydantic import ValidationError

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


@pytest.mark.parametrize(
    "beracun",
    ["Bu Sri Wahyuni", "Jalancagak", "-6.25", "3204012001010001", "KUD Subang"],
)
def test_poisonous_strings_have_nowhere_to_go(golden_request, beracun):
    rusak = deepcopy(golden_request)
    rusak["candidates"][0]["plot_ref"] = beracun

    with pytest.raises(ValidationError):
        ProposeRequest.model_validate(rusak)


def test_the_prompt_never_receives_a_reference(monkeypatch, golden_request, client):
    """Penyedia LLM tidak punya alasan melihat bahkan referensi buram."""
    from app.agent import providers
    from app.config import settings
    from tests.conftest import AUTH

    terlihat: list[str] = []

    async def catat(self, facts):
        terlihat.append(facts.block())
        return ""

    monkeypatch.setattr(providers.OpenRouter, "narrate", catat)
    settings.llm_provider = "openrouter"
    settings.llm_api_key = "kunci-palsu"

    client.post("/v1/plan/propose", json=golden_request, headers=AUTH)

    assert terlihat, "penyedia jarak jauh tidak pernah dipanggil"
    for blok in terlihat:
        assert not re.search(r"\b[pkv]\d+\b", blok), (
            f"blok fakta membocorkan referensi ke penyedia LLM:\n{blok}"
        )
