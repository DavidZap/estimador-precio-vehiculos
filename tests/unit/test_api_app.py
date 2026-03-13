from fastapi.testclient import TestClient

from vehicle_price_estimator.api.main import app


def test_application_health():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "service" in payload
