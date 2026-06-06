from fastapi.testclient import TestClient

from app.api.routes import get_repository_uow_factory, get_scan_job_queue
from app.core.exceptions import QueuePublishError
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


def _client_with_queue(queue: FakeQueue) -> TestClient:
    app = create_app(check_database_on_startup=False)
    app.dependency_overrides[get_scan_job_queue] = lambda: queue
    app.dependency_overrides[get_repository_uow_factory] = lambda: FakeUnitOfWorkFactory()
    return TestClient(app)


def test_enqueue_scan_endpoint_returns_queued_response() -> None:
    queue = FakeQueue()
    response = _client_with_queue(queue).post(f"{API_V1_PREFIX}/packages/lodash/scans")

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "package_name": "lodash",
        "reason": "manual",
    }
    assert queue.scan_calls == [("lodash", "manual")]


def test_enqueue_scan_endpoint_accepts_scoped_package_name() -> None:
    queue = FakeQueue()
    response = _client_with_queue(queue).post(
        f"{API_V1_PREFIX}/packages/@types/node/scans",
        params={"reason": "scheduler"},
    )

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "package_name": "@types/node",
        "reason": "scheduler",
    }
    assert queue.scan_calls == [("@types/node", "scheduler")]


def test_enqueue_scan_endpoint_rejects_invalid_package_name() -> None:
    queue = FakeQueue()
    response = _client_with_queue(queue).post(f"{API_V1_PREFIX}/packages/Bad Name/scans")

    assert response.status_code == 400
    assert response.json() == {"detail": "invalid package name"}
    assert queue.scan_calls == []


def test_legacy_scan_enqueue_endpoint_remains_supported() -> None:
    queue = FakeQueue()
    response = _client_with_queue(queue).post(f"{API_V1_PREFIX}/scans/lodash")

    assert response.status_code == 202
    assert response.json() == {
        "status": "queued",
        "package_name": "lodash",
        "reason": "manual",
    }
    assert queue.scan_calls == [("lodash", "manual")]


def test_enqueue_scan_endpoint_returns_503_when_queue_unavailable() -> None:
    response = _client_with_queue(FakeQueue(fail=True)).post(f"{API_V1_PREFIX}/packages/lodash/scans")

    assert response.status_code == 503
    assert response.json() == {"detail": "scan queue unavailable"}
