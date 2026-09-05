from app.contracts.v1 import CONTRACT_VERSION, ProposeRequest, ProposeResponse


def test_golden_request_parses(golden_request):
    request = ProposeRequest.model_validate(golden_request)

    assert request.contract_version == CONTRACT_VERSION
    assert request.seed == 20260905
    assert request.objectives == ["aman", "pendapatan", "pasar"]
    assert len(request.candidates) == 24
    assert len({c.plot_ref for c in request.candidates}) == 5
    assert request.capacity_tonnes_per_week == 12.5
    assert len(request.demand) == 3


def test_golden_response_parses(golden_response):
    response = ProposeResponse.model_validate(golden_response)

    assert response.contract_version == CONTRACT_VERSION
    assert [p.objective for p in response.plans] == ["aman", "pendapatan", "pasar"]
    assert all(p.narrative for p in response.plans)


def test_unknown_fields_are_ignored(golden_request):
    """Kompatibilitas maju: MINOR yang lebih baru boleh menambah field."""
    forward = golden_request | {"field_yang_belum_ada": {"apa pun": 1}}
    assert ProposeRequest.model_validate(forward).seed == 20260905


def test_demand_weeks_are_mondays(golden_request):
    from datetime import date

    for row in golden_request["demand"]:
        assert date.fromisoformat(row["iso_week"]).weekday() == 0
