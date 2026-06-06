import pytest

from app.core.exceptions import (
    NpmPackageNotFoundError,
    NpmRegistryMalformedResponseError,
    NpmRegistryTimeoutError,
    ScannerLimitExceededError,
    TarballDownloadError,
    TarballExtractError,
    TarballIntegrityError,
    TarballSizeLimitExceededError,
)
from app.worker import tasks as worker_tasks


def test_scan_package_task_retry_configuration() -> None:
    assert worker_tasks.scan_package.autoretry_for == (NpmRegistryTimeoutError, TarballDownloadError)
    assert worker_tasks.scan_package.dont_autoretry_for == (
        NpmPackageNotFoundError,
        NpmRegistryMalformedResponseError,
        ScannerLimitExceededError,
        TarballExtractError,
        TarballIntegrityError,
        TarballSizeLimitExceededError,
    )
    assert worker_tasks.scan_package.retry_backoff is True
    assert worker_tasks.scan_package.retry_jitter is True
    assert worker_tasks.scan_package.retry_kwargs == {"max_retries": 3}


def test_scan_package_task_marks_queue_job_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_mark_running(task_id: str, package_name: str, reason: str) -> None:
        calls.append(("running", task_id))

    async def fake_mark_completed(task_id: str) -> None:
        calls.append(("completed", task_id))

    async def fake_mark_failed(task_id: str, error_message: str) -> None:
        calls.append(("failed", task_id))

    class FakeUseCase:
        async def execute(self, package_name: str, reason: str) -> None:
            return None

    monkeypatch.setattr(worker_tasks, "_mark_queue_job_running", fake_mark_running)
    monkeypatch.setattr(worker_tasks, "_mark_queue_job_completed", fake_mark_completed)
    monkeypatch.setattr(worker_tasks, "_mark_queue_job_failed", fake_mark_failed)
    monkeypatch.setattr(worker_tasks, "_build_scan_use_case", lambda: FakeUseCase())

    result = worker_tasks.scan_package.run(package_name="lodash", reason="manual", task_id="task-123")

    assert result["status"] == "completed"
    assert calls == [("running", "task-123"), ("completed", "task-123")]


def test_scan_package_task_marks_queue_job_failed_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_mark_running(task_id: str, package_name: str, reason: str) -> None:
        calls.append(("running", task_id))

    async def fake_mark_completed(task_id: str) -> None:
        calls.append(("completed", task_id))

    async def fake_mark_failed(task_id: str, error_message: str) -> None:
        calls.append(("failed", task_id))

    class FakeUseCase:
        async def execute(self, package_name: str, reason: str) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(worker_tasks, "_mark_queue_job_running", fake_mark_running)
    monkeypatch.setattr(worker_tasks, "_mark_queue_job_completed", fake_mark_completed)
    monkeypatch.setattr(worker_tasks, "_mark_queue_job_failed", fake_mark_failed)
    monkeypatch.setattr(worker_tasks, "_build_scan_use_case", lambda: FakeUseCase())

    with pytest.raises(RuntimeError, match="boom"):
        worker_tasks.scan_package.run(package_name="lodash", reason="manual", task_id="task-999")

    assert calls == [("running", "task-999"), ("failed", "task-999")]
