import pytest

from app.application.use_cases.enqueue_scan import EnqueueScanUseCase


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def enqueue_scan_package(
        self,
        package_name: str,
        reason: str = "manual",
        *,
        task_id: str | None = None,
    ) -> str:
        self.calls.append((package_name, reason, task_id))
        return task_id or "generated-task-id"

    def enqueue_top_packages_batch(self, limit: int, reason: str = "manual_batch", *, task_id: str | None = None) -> str:
        raise AssertionError("batch enqueue should not be used")


class FakeRepository:
    def __init__(self) -> None:
        self._package_id = 0
        self._scan_result_id = 0
        self.created_jobs: list[tuple[str, str, str | None, str]] = []
        self.created_scans: list[tuple[int, str | None, str | None, str]] = []
        self.failed_jobs: list[tuple[str, str]] = []
        self.failed_scans: list[tuple[int, str]] = []

    async def upsert_package(self, name: str):
        self._package_id += 1
        return type("PackageRow", (), {"id": self._package_id, "name": name})()

    async def create_scan_result(
        self,
        package_id: int,
        latest_version: str | None,
        previous_version: str | None,
        *,
        status: str = "running",
    ):
        self._scan_result_id += 1
        self.created_scans.append((package_id, latest_version, previous_version, status))
        return type("ScanResultRow", (), {"id": self._scan_result_id})()

    async def create_queue_job(
        self,
        *,
        task_id: str,
        job_type: str,
        package_name: str | None,
        reason: str,
    ) -> None:
        self.created_jobs.append((task_id, job_type, package_name, reason))

    async def mark_queue_job_failed(self, *, task_id: str, error_message: str) -> None:
        self.failed_jobs.append((task_id, error_message))

    async def mark_scan_failed(self, scan_result_id: int, error_message: str) -> None:
        self.failed_scans.append((scan_result_id, error_message))


class FakeUnitOfWork:
    def __init__(self, repository: FakeRepository) -> None:
        self._repository = repository

    async def __aenter__(self) -> FakeRepository:
        return self._repository

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeUnitOfWorkFactory:
    def __init__(self, repository: FakeRepository) -> None:
        self._repository = repository

    def __call__(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self._repository)


@pytest.mark.anyio
async def test_enqueue_scan_use_case_enqueues_normalized_payload() -> None:
    queue = FakeQueue()
    repository = FakeRepository()
    use_case = EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(repository))

    task_id = await use_case.execute(" lodash ", " manual ")

    assert queue.calls == [("lodash", "manual", task_id)]
    assert repository.created_jobs == [(task_id, "scan_package", "lodash", "manual")]
    assert repository.created_scans == [(1, None, None, "queued")]
    assert repository.failed_jobs == []


@pytest.mark.anyio
async def test_enqueue_scan_use_case_uses_default_reason_when_empty() -> None:
    queue = FakeQueue()
    repository = FakeRepository()
    use_case = EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(repository))

    task_id = await use_case.execute("lodash", "   ")

    assert queue.calls == [("lodash", "manual", task_id)]
    assert repository.created_jobs == [(task_id, "scan_package", "lodash", "manual")]
    assert repository.created_scans == [(1, None, None, "queued")]


@pytest.mark.parametrize("package_name", ["Lodash", "bad name", "@scope", "pkg/", "@scope/", ""])
@pytest.mark.anyio
async def test_enqueue_scan_use_case_rejects_invalid_package_name(package_name: str) -> None:
    queue = FakeQueue()
    repository = FakeRepository()
    use_case = EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(repository))

    with pytest.raises(ValueError, match="invalid package name"):
        await use_case.execute(package_name)

    assert queue.calls == []
    assert repository.created_jobs == []
