from fastapi.testclient import TestClient

from app.main import create_app


def test_openapi_schema_is_available() -> None:
    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get("/openapi.json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["openapi"].startswith("3.")
    assert payload["info"]["title"] == "npm-sentinel"


def test_swagger_ui_is_available() -> None:
    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get("/docs")

    assert response.status_code == 200
    assert "Swagger UI" in response.text
