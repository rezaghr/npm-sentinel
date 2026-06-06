from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.application.ports.package_repository import FindingRead
from app.infrastructure.db.repositories import SqlAlchemyPackageRepository
from app.main import create_app

API_V1_PREFIX = "/api/v1"


def test_findings_endpoint_supports_severity_and_type_filters(monkeypatch) -> None:
    async def fake_list_findings(self, filters, pagination):
        assert filters.severity == "high"
        assert filters.finding_type == "EXECUTABLE_BINARY"
        assert pagination.limit == 10
        return (
            [
                FindingRead(
                    id=3,
                    scan_result_id=2,
                    package_id=1,
                    package_name="lodash",
                    finding_type="EXECUTABLE_BINARY",
                    severity="high",
                    category="binary",
                    file_path="bin/tool",
                    description="Executable binary found.",
                    evidence="magic:ELF",
                    created_at=datetime(2026, 5, 27, tzinfo=UTC),
                )
            ],
            1,
        )

    monkeypatch.setattr(SqlAlchemyPackageRepository, "list_findings", fake_list_findings)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(
        f"{API_V1_PREFIX}/findings",
        params={"severity": "high", "type": "executable_binary", "limit": 10},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["severity"] == "high"
    assert payload["items"][0]["finding_type"] == "EXECUTABLE_BINARY"
