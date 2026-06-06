from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.application.ports.package_repository import (
    PackageDetail,
    PackageListItem,
    PackageVersionRead,
    ScanResultRead,
)
from app.infrastructure.db.repositories import SqlAlchemyPackageRepository
from app.main import create_app

API_V1_PREFIX = "/api/v1"


def test_packages_endpoint_returns_paginated_data(monkeypatch) -> None:
    async def fake_list_packages(self, filters, pagination):
        assert filters.risk_level == "high"
        assert pagination.limit == 10
        return (
            [
                PackageListItem(
                    id=1,
                    name="lodash",
                    latest_scanned_version="4.17.21",
                    last_scanned_at=datetime(2026, 5, 27, tzinfo=UTC),
                    latest_scan_risk_level="high",
                )
            ],
            1,
        )

    monkeypatch.setattr(SqlAlchemyPackageRepository, "list_packages", fake_list_packages)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(f"{API_V1_PREFIX}/packages", params={"risk_level": "high", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["items"][0]["name"] == "lodash"
    assert payload["items"][0]["latest_scan_risk_level"] == "high"


def test_package_details_endpoint_returns_package_data(monkeypatch) -> None:
    async def fake_get_package_detail(self, name: str):
        return PackageDetail(
            id=1,
            name=name,
            latest_scanned_version="4.17.21",
            last_scanned_at=datetime(2026, 5, 27, tzinfo=UTC),
            latest_scan=ScanResultRead(
                id=7,
                package_id=1,
                package_name=name,
                latest_version="4.17.21",
                previous_version="4.17.20",
                status="completed",
                score=80,
                risk_level="high",
                error_message=None,
                started_at=datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
                finished_at=datetime(2026, 5, 27, 10, 1, tzinfo=UTC),
                created_at=datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
            ),
            versions_count=4,
            findings_count=9,
        )

    monkeypatch.setattr(SqlAlchemyPackageRepository, "get_package_detail", fake_get_package_detail)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(f"{API_V1_PREFIX}/packages/lodash")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "lodash"
    assert payload["latest_scan"]["status"] == "completed"
    assert payload["findings_count"] == 9


def test_package_details_endpoint_returns_404_when_not_found(monkeypatch) -> None:
    async def fake_get_package_detail(self, _: str):
        return None

    monkeypatch.setattr(SqlAlchemyPackageRepository, "get_package_detail", fake_get_package_detail)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(f"{API_V1_PREFIX}/packages/not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": "package not found"}


def test_package_versions_endpoint_returns_metadata(monkeypatch) -> None:
    async def fake_list_package_versions(self, package_name: str, pagination):
        assert package_name == "lodash"
        assert pagination.limit == 2
        return (
            [
                PackageVersionRead(
                    id=10,
                    package_id=1,
                    package_name="lodash",
                    version="4.17.21",
                    published_at=datetime(2026, 5, 27, tzinfo=UTC),
                    tarball_url="https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                    integrity="sha512-example",
                    unpacked_size=123456,
                    file_count=42,
                    package_json={"name": "lodash", "version": "4.17.21"},
                    dependencies={"node": ">=18"},
                    scripts={"postinstall": "node setup.js"},
                    created_at=datetime(2026, 5, 27, tzinfo=UTC),
                )
            ],
            1,
        )

    monkeypatch.setattr(SqlAlchemyPackageRepository, "list_package_versions", fake_list_package_versions)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(f"{API_V1_PREFIX}/package-versions/lodash", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["version"] == "4.17.21"
    assert payload["items"][0]["unpacked_size"] == 123456
    assert payload["items"][0]["scripts"]["postinstall"] == "node setup.js"


def test_package_versions_endpoint_returns_404_when_not_found(monkeypatch) -> None:
    async def fake_list_package_versions(self, package_name: str, pagination):
        return [], 0

    monkeypatch.setattr(SqlAlchemyPackageRepository, "list_package_versions", fake_list_package_versions)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(f"{API_V1_PREFIX}/package-versions/not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": "package not found"}
