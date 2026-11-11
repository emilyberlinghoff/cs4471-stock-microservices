"""These run when Flask is installed from requirements-dev.txt."""
from datetime import date

import pytest

flask = pytest.importorskip("flask")
from app import create_app
from stock_returns import ServiceError


class StubService:
    def run(self, symbol, start_date, end_date):
        if symbol is None or start_date is None or end_date is None:
            raise ServiceError("MISSING_INPUT", "Missing required input.", 400)
        return {"service_id": "S2", "symbol": symbol,
                "requested_start_date": start_date, "requested_end_date": end_date,
                "effective_start_date": start_date, "effective_end_date": end_date,
                "price_basis": "raw_close", "number_of_returns": 1,
                "returns": [{"date": end_date, "return_percent": 1.5}]}


@pytest.fixture
def client():
    app = create_app(StubService())
    app.testing = True
    return app.test_client()


def test_get_valid(client):
    response = client.get("/api/v1/stock-returns?symbol=IBM&start_date=2026-01-05&end_date=2026-01-06")
    assert response.status_code == 200
    assert response.json["returns"][0]["return_percent"] == 1.5


def test_post_valid(client):
    response = client.post("/api/v1/stock-returns", json={"symbol": "IBM",
                           "start_date": "2026-01-05", "end_date": "2026-01-06"})
    assert response.status_code == 200
    assert response.json["service_id"] == "S2"


def test_errors_have_structured_code_and_message(client):
    response = client.get("/api/v1/stock-returns?symbol=IBM")
    assert response.status_code == 400
    assert response.json == {"error": {"code": "MISSING_INPUT", "message": "Missing required input."}}


def test_invalid_post_json(client):
    response = client.post("/api/v1/stock-returns", data="bad", content_type="application/json")
    assert response.status_code == 400
    assert response.json["error"]["code"] == "INVALID_INPUT"


def test_health_and_service_info(client, monkeypatch):
    monkeypatch.setenv("SERVICE_PUBLIC_URL", "https://s2.example.org")
    assert client.get("/health").json["status"] == "ok"
    info = client.get("/service-info").json
    assert info["id"] == "S2"
    assert info["url"] == "https://s2.example.org/api/v1/stock-returns"
