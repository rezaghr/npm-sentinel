from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.routes import get_repository_uow_factory, get_scan_job_queue, get_top_packages_source
from app.application.ports.package_repository import ScanResultRead
from app.core.exceptions import QueuePublishError
from app.infrastructure.db.repositories import SqlAlchemyPackageRepository
from app.main import create_app

API_V1_PREFIX = "/api/v1"


class FakeQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.scan_calls: list[tuple[str, str]] = []
        self.batch_calls: list[tuple[int, str]] = []

    def enqueue_scan_package(
        self,
        package_name: str,
        reason: str = "manual",
        *,
        task_id: str | None = None,
    ) -> str:
        if self.fail:
            raise QueuePublishError("scan queue unavailable")
        self.scan_calls.append((package_name, reason))
        return task_id or "fake-task-id"

    def enqueue_top_packages_batch(self, limit: int, reason: str = "manual_batch", *, task_id: str | None = None) -> str:
        self.batch_calls.append((limit, reason))
        return task_id or "fake-batch-task-id"


class FakeTopPackagesSource:
    def __init__(self, package_names: list[str]) -> None:
        self.package_names = package_names

    async def load_package_names(self, limit: int | None = None) -> list[str]:
        if limit is None:
            return list(self.package_names)
        return list(self.package_names[:limit])


class FakeRepository:
    async def upsert_package(self, name: str):
        return type("PackageRow", (), {"id": 1, "name": name})()

    async def create_scan_result(
        self,
        package_id: int,
        latest_version: str | None,
        previous_version: str | None,
        *,
        status: str = "running",
    ):
        return type("ScanResultRow", (), {"id": 1})()

    async def create_queue_job(self, *, task_id: str, job_type: str, package_name: str | None, reason: str) -> None:
        return None

    async def mark_queue_job_failed(self, *, task_id: str, error_message: str) -> None:
        return None

    async def mark_scan_failed(self, scan_result_id: int, error_message: str) -> None:
        return None


class FakeUnitOfWork:
    async def __aenter__(self) -> FakeRepository:
        return FakeRepository()

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeUnitOfWorkFactory:
    def __call__(self) -> FakeUnitOfWork:
        return FakeUnitOfWork()


def _client_with_queue(
    queue: FakeQueue,
    *,
    package_names: list[str] | None = None,
) -> TestClient:
    app = create_app(check_database_on_startup=False)
    app.dependency_overrides[get_scan_job_queue] = lambda: queue
    app.dependency_overrides[get_repository_uow_factory] = lambda: FakeUnitOfWorkFactory()
    app.dependency_overrides[get_top_packages_source] = lambda: FakeTopPackagesSource(
        package_names or ["pkg-a", "pkg-b", "pkg-c"]
    )
    return TestClient(app)


def test_scans_endpoint_supports_status_filter(monkeypatch) -> None:
    async def fake_list_scan_results(self, filters, pagination):
        assert filters.status == "failed"
        assert pagination.limit == 5
        return (
            [
                ScanResultRead(
                    id=11,
                    package_id=1,
                    package_name="lodash",
                    latest_version="4.17.21",
                    previous_version="4.17.20",
                    status="failed",
                    score=None,
                    risk_level="unknown",
                    error_message="registry timeout",
                    started_at=datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
                    finished_at=datetime(2026, 5, 27, 10, 1, tzinfo=UTC),
                    created_at=datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
                )
            ],
            1,
        )

    monkeypatch.setattr(SqlAlchemyPackageRepository, "list_scan_results", fake_list_scan_results)

    app = create_app(check_database_on_startup=False)
    response = TestClient(app).get(f"{API_V1_PREFIX}/scans", params={"status": "failed", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["status"] == "failed"


def test_scan_batch_endpoint_enqueues_batch_job() -> None:
    queue = FakeQueue()
    response = _client_with_queue(queue).post(
        f"{API_V1_PREFIX}/scan-batches",
        json={"source": "top_packages", "limit": 15},
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "source": "top_packages",
        "requested": 3,
        "enqueued": 3,
        "skipped": 0,
        "reason": "manual_batch",
    }
    assert queue.batch_calls == []
    assert queue.scan_calls == [
        ("pkg-a", "manual_batch"),
        ("pkg-b", "manual_batch"),
        ("pkg-c", "manual_batch"),
    ]


def test_legacy_top_packages_enqueue_endpoint_is_supported() -> None:
    queue = FakeQueue()
    response = _client_with_queue(queue).post(
        f"{API_V1_PREFIX}/scans/top-packages",
        params={"limit": 12, "reason": "scheduler"},
    )

    assert response.status_code == 202
    assert response.json()["requested"] == 3
    assert response.json()["enqueued"] == 3
    assert queue.batch_calls == []
    assert queue.scan_calls == [("pkg-a", "scheduler"), ("pkg-b", "scheduler"), ("pkg-c", "scheduler")]


def test_scan_batch_endpoint_returns_503_when_queue_unavailable() -> None:
    response = _client_with_queue(FakeQueue(fail=True)).post(
        f"{API_V1_PREFIX}/scan-batches",
        json={"source": "top_packages"},
    )

    assert response.status_code == 503
    assert response.json() == {"detail": "scan queue unavailable"}


def test_scan_batch_endpoint_skips_invalid_package_names() -> None:
    queue = FakeQueue()
    response = _client_with_queue(
        queue,
        package_names=["pkg-a", "JSONStream", "pkg-b"],
    ).post(
        f"{API_V1_PREFIX}/scan-batches",
        json={"source": "top_packages", "limit": 3},
    )

    assert response.status_code == 202
    assert response.json()["requested"] == 3
    assert response.json()["enqueued"] == 2
    assert response.json()["skipped"] == 1
    assert queue.scan_calls == [("pkg-a", "manual_batch"), ("pkg-b", "manual_batch")]
