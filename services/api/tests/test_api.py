from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_emulator_readiness() -> None:
    client = TestClient(create_app(Settings(serving_mode="emulator")))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "servingMode": "emulator",
        "missingLiveFields": [],
    }


def test_serve_endpoint_returns_pipeline_decision_contract() -> None:
    client = TestClient(create_app(Settings(serving_mode="emulator")))

    response = client.post(
        "/api/serve",
        json={
            "useCase": "recommendations",
            "userId": "u-ada",
            "query": "trail jacket for rainy commute",
            "category": "Outerwear",
            "maxPrice": 160,
            "productId": "p-trail-jacket",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["serviceMode"] == "emulator"
    assert body["useCase"] == "recommendations"
    assert body["results"][0]["product"]["productId"] == "p-trail-jacket"
    assert body["freshness"]["rows"][0]["entityKey"] == "item#p-trail-jacket"
    assert body["trace"][-1]["service"] == "Vertex AI"


def test_serve_endpoint_rejects_invalid_price_boundary() -> None:
    client = TestClient(create_app(Settings(serving_mode="emulator")))

    response = client.post(
        "/api/serve",
        json={
            "useCase": "search",
            "query": "trail jacket",
            "maxPrice": 0,
            "productId": "p-trail-jacket",
        },
    )

    assert response.status_code == 422
    assert "greater than 0" in response.text


def test_event_endpoint_publishes_and_exposes_updated_feature() -> None:
    client = TestClient(create_app(Settings(serving_mode="emulator")))

    response = client.post(
        "/api/events",
        json={
            "productId": "p-trail-jacket",
            "eventType": "product_viewed",
            "occurredAt": "2026-06-04T17:00:15Z",
        },
    )

    body = response.json()
    assert response.status_code == 200
    assert body["eventId"].startswith("emulator-")
    assert body["updatedFeature"]["entityKey"] == "item#p-trail-jacket"
    assert body["updatedFeature"]["stalenessSeconds"] == 0
