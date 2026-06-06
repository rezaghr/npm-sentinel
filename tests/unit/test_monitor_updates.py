import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.application.ports.package_registry import PackageRegistryMetadata, PackageVersionMetadata
from app.application.use_cases.enqueue_scan import EnqueueScanUseCase
from app.application.use_cases.monitor_updates import MonitorUpdatesUseCase, PackageMonitorError, PackageScanState
from app.application.ports.queue import ScanJobQueue


class FakeQueue(ScanJobQueue):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def enqueue_scan_package(
        self,
        package_name: str,
        reason: str = "manual",
        *,
        task_id: str | None = None,
    ) -> str:
        self.calls.append((package_name, reason))
        return task_id or f"{package_name}-task"

    def enqueue_top_packages_batch(self, limit: int, reason: str = "manual_batch", *, task_id: str | None = None) -> str:
        raise AssertionError("batch enqueue should not be used")


@dataclass
class FakeQueueJobRepository:
    created_jobs: list[tuple[str, str, str | None, str]]
    created_scans: list[tuple[int, str]]
    failed_scans: list[tuple[int, str]]

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
        self.created_scans.append((package_id, status))
        return type("ScanResultRow", (), {"id": len(self.created_scans)})()

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
        return None

    async def mark_scan_failed(self, scan_result_id: int, error_message: str) -> None:
        self.failed_scans.append((scan_result_id, error_message))


class FakeUnitOfWork:
    def __init__(self, repository: FakeQueueJobRepository) -> None:
        self._repository = repository

    async def __aenter__(self) -> FakeQueueJobRepository:
        return self._repository

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class FakeUnitOfWorkFactory:
    def __init__(self, repository: FakeQueueJobRepository) -> None:
        self._repository = repository

    def __call__(self) -> FakeUnitOfWork:
        return FakeUnitOfWork(self._repository)


class FakePackageListSource:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    async def load_package_names(self, limit: int | None = None) -> list[str]:
        if limit is None:
            return self.names
        return self.names[:limit]


class FakePackageRegistry:
    def __init__(
        self,
        metadata_by_name: dict[str, PackageRegistryMetadata],
        error_by_name: dict[str, Exception] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self._metadata_by_name = metadata_by_name
        self._error_by_name = error_by_name or {}
        self._delay_seconds = delay_seconds
        self.max_in_flight = 0
        self._in_flight = 0

    async def fetch_metadata(self, package_name: str) -> PackageRegistryMetadata:
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self._delay_seconds:
                await asyncio.sleep(self._delay_seconds)
            if package_name in self._error_by_name:
                raise self._error_by_name[package_name]
            return self._metadata_by_name[package_name]
        finally:
            self._in_flight -= 1


def _metadata(package_name: str, latest_version: str) -> PackageRegistryMetadata:
    return PackageRegistryMetadata(
        package_name=package_name,
        latest_version=PackageVersionMetadata(
            package_name=package_name,
            version=latest_version,
            published_at=datetime.now(UTC),
            tarball_url=f"https://example.test/{package_name}-{latest_version}.tgz",
            integrity=None,
            unpacked_size=None,
            file_count=None,
            package_json={},
            dependencies={},
            scripts={},
        ),
        previous_version=None,
    )


@pytest.mark.anyio
async def test_monitor_updates_result_counts_new_updated_unchanged() -> None:
    queue = FakeQueue()
    queue_job_repository = FakeQueueJobRepository(created_jobs=[], created_scans=[], failed_scans=[])
    use_case = MonitorUpdatesUseCase(
        package_list_source=FakePackageListSource(["new-pkg", "updated-pkg", "unchanged-pkg"]),
        package_registry=FakePackageRegistry(
            {
                "new-pkg": _metadata("new-pkg", "1.0.0"),
                "updated-pkg": _metadata("updated-pkg", "2.0.0"),
                "unchanged-pkg": _metadata("unchanged-pkg", "3.0.0"),
            }
        ),
        enqueue_scan_use_case=EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(queue_job_repository)),
        load_package_scan_state=lambda package_name: asyncio.sleep(
            0,
            result={
                "new-pkg": PackageScanState(package_id=None, latest_scanned_version=None),
                "updated-pkg": PackageScanState(package_id=2, latest_scanned_version="1.0.0"),
                "unchanged-pkg": PackageScanState(package_id=3, latest_scanned_version="3.0.0"),
            }[package_name],
        ),
        has_running_scan=lambda _: asyncio.sleep(0, result=False),
        top_package_limit=20,
        metadata_concurrency=5,
        skip_running_scans=False,
    )

    result = await use_case.execute_once()

    assert result.checked_count == 3
    assert result.enqueued_new_count == 1
    assert result.enqueued_updated_count == 1
    assert result.unchanged_count == 1
    assert result.failed_count == 0
    assert result.errors == []
    assert queue.calls == [("new-pkg", "scheduler"), ("updated-pkg", "scheduler")]


@pytest.mark.anyio
async def test_monitor_updates_isolates_metadata_failure() -> None:
    queue = FakeQueue()
    queue_job_repository = FakeQueueJobRepository(created_jobs=[], created_scans=[], failed_scans=[])
    use_case = MonitorUpdatesUseCase(
        package_list_source=FakePackageListSource(["ok-a", "bad", "ok-b"]),
        package_registry=FakePackageRegistry(
            {
                "ok-a": _metadata("ok-a", "1.0.0"),
                "bad": _metadata("bad", "1.0.0"),
                "ok-b": _metadata("ok-b", "1.0.0"),
            },
            error_by_name={"bad": RuntimeError("metadata failed")},
        ),
        enqueue_scan_use_case=EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(queue_job_repository)),
        load_package_scan_state=lambda package_name: asyncio.sleep(
            0,
            result=PackageScanState(package_id=None, latest_scanned_version=None),
        ),
        has_running_scan=lambda _: asyncio.sleep(0, result=False),
        top_package_limit=20,
        metadata_concurrency=5,
        skip_running_scans=False,
    )

    result = await use_case.execute_once()

    assert result.checked_count == 2
    assert result.enqueued_new_count == 2
    assert result.failed_count == 1
    assert result.errors == [PackageMonitorError(package_name="bad", error="metadata failed")]
    assert queue.calls == [("ok-a", "scheduler"), ("ok-b", "scheduler")]


@pytest.mark.anyio
async def test_monitor_updates_uses_bounded_metadata_concurrency() -> None:
    names = [f"pkg-{index}" for index in range(6)]
    queue = FakeQueue()
    queue_job_repository = FakeQueueJobRepository(created_jobs=[], created_scans=[], failed_scans=[])
    registry = FakePackageRegistry(
        {name: _metadata(name, "1.0.0") for name in names},
        delay_seconds=0.01,
    )
    use_case = MonitorUpdatesUseCase(
        package_list_source=FakePackageListSource(names),
        package_registry=registry,
        enqueue_scan_use_case=EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(queue_job_repository)),
        load_package_scan_state=lambda _: asyncio.sleep(0, result=PackageScanState(None, None)),
        has_running_scan=lambda _: asyncio.sleep(0, result=False),
        top_package_limit=20,
        metadata_concurrency=2,
        skip_running_scans=False,
    )

    result = await use_case.execute_once()

    assert result.checked_count == len(names)
    assert registry.max_in_flight <= 2


@pytest.mark.anyio
async def test_monitor_updates_can_skip_packages_with_running_scans() -> None:
    queue = FakeQueue()
    queue_job_repository = FakeQueueJobRepository(created_jobs=[], created_scans=[], failed_scans=[])
    use_case = MonitorUpdatesUseCase(
        package_list_source=FakePackageListSource(["pkg-running"]),
        package_registry=FakePackageRegistry({"pkg-running": _metadata("pkg-running", "2.0.0")}),
        enqueue_scan_use_case=EnqueueScanUseCase(queue, FakeUnitOfWorkFactory(queue_job_repository)),
        load_package_scan_state=lambda _: asyncio.sleep(
            0, result=PackageScanState(package_id=7, latest_scanned_version="1.0.0")
        ),
        has_running_scan=lambda _: asyncio.sleep(0, result=True),
        top_package_limit=20,
        metadata_concurrency=1,
        skip_running_scans=True,
    )

    result = await use_case.execute_once()

    assert result.checked_count == 1
    assert result.skipped_running_count == 1
    assert result.enqueued_new_count == 0
    assert result.enqueued_updated_count == 0
    assert queue.calls == []
