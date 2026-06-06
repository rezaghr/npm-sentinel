from kombu.exceptions import KombuError

from app.core.exceptions import QueuePublishError
from app.application.ports.queue import ScanJobQueue
from app.worker.celery_app import celery_app

_SCAN_PACKAGE_TASK_NAME = "app.worker.tasks.scan_package"
_ENQUEUE_TOP_PACKAGES_TASK_NAME = "app.worker.tasks.enqueue_top_packages"


class CeleryScanJobQueue(ScanJobQueue):
    def enqueue_scan_package(
        self,
        package_name: str,
        reason: str = "manual",
        *,
        task_id: str | None = None,
    ) -> str:
        return self._send_task(
            _SCAN_PACKAGE_TASK_NAME,
            kwargs={"package_name": package_name, "reason": reason},
            task_id=task_id,
        )

    def enqueue_top_packages_batch(
        self,
        limit: int,
        reason: str = "manual_batch",
        *,
        task_id: str | None = None,
    ) -> str:
        return self._send_task(
            _ENQUEUE_TOP_PACKAGES_TASK_NAME,
            kwargs={"limit": limit, "reason": reason},
            task_id=task_id,
        )

    @staticmethod
    def _send_task(task_name: str, *, kwargs: dict[str, object], task_id: str | None = None) -> str:
        try:
            result = celery_app.send_task(task_name, kwargs=kwargs, task_id=task_id)
        except (KombuError, OSError) as exc:
            raise QueuePublishError("scan queue unavailable") from exc
        return result.id
