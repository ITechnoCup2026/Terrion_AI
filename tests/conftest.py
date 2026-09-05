import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "token-uji"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _configured():
    settings.ai_service_token = TOKEN
    settings.llm_provider = "template"
    settings.llm_api_key = ""
    settings.monte_carlo_draws = 2000
    yield


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def golden_request():
    return json.loads((FIXTURES / "propose_request.golden.json").read_text())


@pytest.fixture
def golden_response():
    return json.loads((FIXTURES / "propose_response.golden.json").read_text())


@pytest.fixture
def problem(golden_request):
    from app.contracts.v1 import ProposeRequest
    from app.problem import Problem

    return Problem.from_request(ProposeRequest.model_validate(golden_request))
