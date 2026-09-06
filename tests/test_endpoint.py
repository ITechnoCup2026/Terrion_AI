from copy import deepcopy

from tests.conftest import AUTH


def test_health_needs_no_token(client):
    assert client.get("/health").status_code == 200


def test_ready_reports_the_contract_version(client):
    body = client.get("/ready").json()

    assert body["contract_version"] == "1.0"
    # Fase 2: CP-SAT terpasang sebagai dependensi utama, jadi /ready harus
    # mengakuinya. Kalau ini gagal, ortools hilang dari lingkungan dan
    # layanan diam-diam turun ke solver cadangan.
    assert body["cpsat"] is True


def test_propose_without_a_token_is_rejected(client, golden_request):
    assert client.post("/v1/plan/propose", json=golden_request).status_code == 401


def test_propose_with_a_wrong_token_is_rejected(client, golden_request):
    response = client.post(
        "/v1/plan/propose", json=golden_request, headers={"Authorization": "Bearer salah"}
    )

    assert response.status_code == 401


def test_a_major_version_mismatch_is_refused_loudly(client, golden_request):
    """Deploy yang tidak seiring harus gagal berisik, bukan diam."""
    other = golden_request | {"contract_version": "2.0"}
    response = client.post("/v1/plan/propose", json=other, headers=AUTH)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "contract_version_unsupported"


def test_a_malformed_request_uses_the_error_envelope(client, golden_request):
    rusak = deepcopy(golden_request)
    rusak["candidates"][0]["tonnes_low"] = 999.0

    response = client.post("/v1/plan/propose", json=rusak, headers=AUTH)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "malformed_request"


def test_every_requested_objective_gets_an_entry_in_order(client, golden_request):
    body = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()

    assert [p["objective"] for p in body["plans"]] == golden_request["objectives"]


def test_one_planting_per_plot(client, golden_request, problem):
    body = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()

    for plan in body["plans"]:
        plots = [problem.by_id[i].plot_ref for i in plan["candidate_ids"]]
        assert len(plots) == len(set(plots)), "satu lahan ditanami dua kali"


def test_dominance_invariants_hold(client, golden_request):
    """Tiga rencana harus berbeda jenisnya, bukan hanya berbeda bobotnya.

    Kalau baris mana pun di sini gagal, skalarisasinya salah — bukan sekadar
    kurang optimal.
    """
    body = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()
    by_objective = {p["objective"]: p["metrics"] for p in body["plans"]}

    peak = {k: m["peak_tonnes_p90"] for k, m in by_objective.items()}
    value = {k: m["gross_value"] for k, m in by_objective.items()}
    covered = {k: m["demand_covered_kg"] for k, m in by_objective.items()}

    assert peak["aman"] <= min(peak["pendapatan"], peak["pasar"])
    assert value["pendapatan"] >= max(value["aman"], value["pasar"])
    assert covered["pasar"] >= max(covered["aman"], covered["pendapatan"])


def test_every_plan_is_narrated_without_an_llm(client, golden_request):
    body = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()

    for plan in body["plans"]:
        assert plan["narrative"]
        assert plan["narrative_source"] == "template"
    assert body["diagnostics"]["degraded"] == []


def test_a_single_objective_request_is_honoured(client, golden_request):
    other = golden_request | {"objectives": ["pasar"]}
    body = client.post("/v1/plan/propose", json=other, headers=AUTH).json()

    assert len(body["plans"]) == 1
    assert body["plans"][0]["objective"] == "pasar"


def test_a_request_with_no_demand_still_returns_three_plans(client, golden_request):
    other = golden_request | {"demand": []}
    body = client.post("/v1/plan/propose", json=other, headers=AUTH).json()

    assert len(body["plans"]) == 3
    assert all(p["metrics"]["demand_covered_kg"] == 0 for p in body["plans"])


def test_a_too_large_request_says_which_limit_it_broke(client, golden_request):
    """Regresi produksi: `422` yang tidak menyebut apa-apa tak bisa didiagnosis.

    Di Railway, lima `422 Unprocessable Entity` beruntun pada
    `/v1/plan/propose` hanya memberi kodenya. Ketiga batas — 2000 kandidat,
    400 baris permintaan, 3 objektif — jatuh ke pesan yang persis sama, dan
    penangannya tidak menulis satu baris log pun. Tidak ada cara mengetahui
    batas mana yang dilanggar tanpa menebak. Pesannya harus menyebut field
    dan angkanya.
    """
    rusak = deepcopy(golden_request)
    contoh = rusak["candidates"][0]
    rusak["candidates"] = [contoh | {"id": f"c{i + 10000}"} for i in range(2001)]

    response = client.post("/v1/plan/propose", json=rusak, headers=AUTH)
    pesan = response.json()["error"]["message"]

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "problem_too_large"
    assert "candidates" in pesan
    assert "2001" in pesan and "2000" in pesan


def test_a_too_large_demand_names_demand_and_not_candidates(client, golden_request):
    """Batas yang berbeda harus bisa dibedakan dari pesannya saja."""
    rusak = deepcopy(golden_request)
    rusak["demand"] = [rusak["demand"][0]] * 401

    pesan = client.post("/v1/plan/propose", json=rusak, headers=AUTH).json()["error"]["message"]

    assert "demand" in pesan
    assert "candidates" not in pesan


def test_a_malformed_request_says_which_field_is_wrong(client, golden_request):
    """`400` menanggung masalah yang sama: sisi Go butuh nama fieldnya."""
    rusak = deepcopy(golden_request)
    rusak["candidates"][3]["plot_ref"] = "lahan-7"

    pesan = client.post("/v1/plan/propose", json=rusak, headers=AUTH).json()["error"]["message"]

    assert "candidates" in pesan and "plot_ref" in pesan
