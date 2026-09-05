from tests.conftest import AUTH


def test_two_identical_requests_produce_identical_responses(client, golden_request):
    first = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()
    second = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()

    for body in (first, second):
        body.pop("elapsed_ms")
        body.pop("request_id")

    assert first == second


def test_response_matches_the_golden_file(client, golden_request, golden_response):
    """Perubahan perilaku solver harus terlihat sebagai perubahan berkas emas."""
    body = client.post("/v1/plan/propose", json=golden_request, headers=AUTH).json()
    body["elapsed_ms"] = 0

    assert body == golden_response


def test_a_different_seed_may_change_the_plan_but_not_its_validity(client, golden_request):
    other = golden_request | {"seed": golden_request["seed"] + 1}
    body = client.post("/v1/plan/propose", json=other, headers=AUTH).json()

    for plan in body["plans"]:
        assert len(set(plan["candidate_ids"])) == len(plan["candidate_ids"])
        assert plan["metrics"]["peak_tonnes_p90"] >= plan["metrics"]["peak_tonnes_p50"]
