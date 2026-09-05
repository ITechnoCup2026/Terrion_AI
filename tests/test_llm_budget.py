"""Kenapa narasi model kehabisan waktu, dan apa yang menjaganya tetap muat.

Diukur langsung ke penyedia (gpt-5.4-nano lewat Sumopod, koneksi hangat):
token pertama tiba pada 720-830 ms, lalu model menulis ~190 token dengan
laju ~6,5 ms/token. Satu panggilan yang wajar memakan 2,4-2,7 detik di
dalam anggaran 2,8 detik — margin di bawah setengah detik, dan ekornya
terukur sampai 4,2 detik. Dua biaya yang bisa dihindari mendorong kasus
lazim itu melewati tebing; dua berkas uji di bawah menjaga keduanya.
"""

import httpx

from app.agent import providers
from app.agent.facts import Facts
from app.config import settings


def pool_keepalive(client: httpx.AsyncClient) -> float | None:
    """Berapa lama kolam koneksi klien menahan koneksi yang menganggur."""
    return client._transport._pool._keepalive_expiry


def test_the_shared_client_survives_the_gap_between_two_requests():
    """Bawaan httpx membuang koneksi menganggur setelah 5 detik.

    Layanan ini menerima permintaan dengan jarak menit, bukan detik, jadi
    dengan bawaan itu setiap permintaan membayar ulang handshake TLS dan
    janji di docstring shared_client() tidak pernah ditepati. Diukur: satu
    ping setelah menganggur 12 detik memakan 806 ms dengan bawaan httpx,
    dan 69 ms tanpa kedaluwarsa.
    """
    providers._client = None
    client = providers.shared_client()

    expiry = pool_keepalive(client)
    assert expiry is None or expiry >= 60, (
        f"koneksi menganggur dibuang setelah {expiry}s — setiap permintaan "
        f"akan membayar handshake TLS lagi di dalam anggaran narasi"
    )


def test_the_prompt_tells_the_model_how_long_the_paragraph_may_be(problem, golden_response):
    """Prompt yang tidak membatasi panjang membuat model menulis dua kali lipat.

    Diminta "2-4 kalimat", model mengembalikan ~190 token / ~720 karakter.
    Dengan batas yang disebut eksplisit ia menulis ~145 token / ~520
    karakter, dan gelombang tiga narasi turun dari 2,4-2,7 detik menjadi
    1,75-2,0 detik.
    """
    from app.contracts.v1 import PlanResult

    plan = PlanResult.model_validate(golden_response["plans"][0])
    prompt = providers.render_prompt(Facts.from_plan(plan, problem))

    assert str(providers.MAX_NARRATIVE_CHARS) in prompt, (
        "prompt tidak menyebut batas panjang, jadi model bebas menulis "
        "sepanjang yang ia mau — dan waktunya diambil dari anggaran narasi"
    )


def test_the_token_budget_leaves_room_for_the_paragraph_the_prompt_asks_for():
    """max_tokens yang terlalu ketat menolak narasi, bukan mempercepatnya.

    Diukur: max_tokens=180 dan 120 dijawab finish_reason "length", dan
    penjaga menolak jawaban terpotong. Jadi anggaran token harus duduk di
    atas paragraf terpanjang yang prompt izinkan, bukan di bawahnya.
    """
    # ~3,3 karakter per token untuk teks Indonesia, diukur dari jawaban
    # sungguhan: 190 token untuk 720 karakter.
    tokens_needed = providers.MAX_NARRATIVE_CHARS / 3.3

    assert settings.llm_max_tokens >= tokens_needed * 1.5, (
        f"{settings.llm_max_tokens} token tidak cukup untuk paragraf "
        f"{providers.MAX_NARRATIVE_CHARS} karakter — jawaban akan terpotong "
        f"dan penjaga menolaknya"
    )
