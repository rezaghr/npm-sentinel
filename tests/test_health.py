from fastapi.testclient import TestClient

from app.main import create_app

API_V1_PREFIX = "/api/v1"


def test_health_endpoint_returns_ok() -> None:
    app = create_app(check_database_on_startup=False)

    response = TestClient(app).get(f"{API_V1_PREFIX}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "npm-sentinel-api"}
