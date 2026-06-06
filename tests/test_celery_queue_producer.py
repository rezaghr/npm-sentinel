import pytest

from app.core.exceptions import QueuePublishError
from app.infrastructure.queue.producer import CeleryScanJobQueue


def test_celery_scan_job_queue_sends_expected_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object], str | None]] = []

    class FakeAsyncResult:
        def __init__(self, task_id: str | None) -> None:
            self.id = task_id or "generated-task-id"

    def fake_send_task(task_name: str, kwargs: dict[str, object], task_id: str | None = None) -> FakeAsyncResult:
        calls.append((task_name, kwargs, task_id))
        return FakeAsyncResult(task_id)

    monkeypatch.setattr("app.infrastructure.queue.producer.celery_app.send_task", fake_send_task)

    queue = CeleryScanJobQueue()
    task_id = queue.enqueue_scan_package("lodash", "manual", task_id="task-1")

    assert calls == [
        (
            "app.worker.tasks.scan_package",
            {"package_name": "lodash", "reason": "manual"},
            "task-1",
        )
    ]
    assert task_id == "task-1"


def test_celery_scan_job_queue_sends_batch_payload(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object], str | None]] = []

    class FakeAsyncResult:
        def __init__(self, task_id: str | None) -> None:
            self.id = task_id or "generated-task-id"

    def fake_send_task(task_name: str, kwargs: dict[str, object], task_id: str | None = None) -> FakeAsyncResult:
        calls.append((task_name, kwargs, task_id))
        return FakeAsyncResult(task_id)

    monkeypatch.setattr("app.infrastructure.queue.producer.celery_app.send_task", fake_send_task)

    queue = CeleryScanJobQueue()
    task_id = queue.enqueue_top_packages_batch(10, "scheduler", task_id="batch-1")

    assert calls == [
        (
            "app.worker.tasks.enqueue_top_packages",
            {"limit": 10, "reason": "scheduler"},
            "batch-1",
        )
    ]
    assert task_id == "batch-1"


def test_celery_scan_job_queue_translates_publish_failure(monkeypatch) -> None:
    def fake_send_task(task_name: str, kwargs: dict[str, object], task_id: str | None = None) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr("app.infrastructure.queue.producer.celery_app.send_task", fake_send_task)

    queue = CeleryScanJobQueue()
    with pytest.raises(QueuePublishError, match="scan queue unavailable"):
        queue.enqueue_scan_package("lodash", "manual")
