import re
import logging
from uuid import uuid4

from app.application.ports.queue import ScanJobQueue
from app.application.ports.unit_of_work import RepositoryUnitOfWorkFactory
from app.core.exceptions import QueuePublishError

_PACKAGE_NAME_PATTERN = re.compile(
    r"^(?:@[a-z0-9~][a-z0-9._~-]*/)?[a-z0-9~][a-z0-9._~-]*$"
)
logger = logging.getLogger(__name__)


def is_valid_package_name(package_name: str) -> bool:
    return bool(_PACKAGE_NAME_PATTERN.fullmatch(package_name))


class EnqueueScanUseCase:
    def __init__(self, queue: ScanJobQueue, repository_unit_of_work_factory: RepositoryUnitOfWorkFactory) -> None:
        self._queue = queue
        self._repository_unit_of_work_factory = repository_unit_of_work_factory

    async def execute(self, package_name: str, reason: str = "manual") -> str:
        normalized_package_name = package_name.strip()
        normalized_reason = reason.strip() or "manual"

        if not is_valid_package_name(normalized_package_name):
            raise ValueError("invalid package name")

        task_id = uuid4().hex
        scan_result_id: int | None = None
        async with self._repository_unit_of_work_factory() as repository:
            package = await repository.upsert_package(normalized_package_name)
            scan_result = await repository.create_scan_result(
                package.id,
                latest_version=None,
                previous_version=None,
                status="queued",
            )
            scan_result_id = scan_result.id
            await repository.create_queue_job(
                task_id=task_id,
                job_type="scan_package",
                package_name=normalized_package_name,
                reason=normalized_reason,
            )

        try:
            self._queue.enqueue_scan_package(normalized_package_name, normalized_reason, task_id=task_id)
        except QueuePublishError:
            async with self._repository_unit_of_work_factory() as repository:
                await repository.mark_queue_job_failed(
                    task_id=task_id,
                    error_message="scan queue unavailable",
                )
                if scan_result_id is not None:
                    await repository.mark_scan_failed(
                        scan_result_id,
                        error_message="scan queue unavailable",
                    )
            raise

        logger.info(
            "job_enqueued",
            extra={
                "task_id": task_id,
                "package_name": normalized_package_name,
                "job_reason": normalized_reason,
            },
        )
        return task_id
