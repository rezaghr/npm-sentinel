import asyncio
import logging
from uuid import uuid4

from app.application.use_cases.enqueue_scan import EnqueueScanUseCase
from app.application.use_cases.enqueue_top_packages_batch import EnqueueTopPackagesBatchUseCase
from app.application.use_cases.scan_package import ScanPackageUseCase
from app.core.config import get_settings
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
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyRepositoryUnitOfWorkFactory
from app.infrastructure.npm.registry_client import NpmRegistryClient
from app.infrastructure.npm.tarball_downloader import TarballDownloader
from app.infrastructure.package_list.meyond_top_packages_source import MeyondTopPackagesSource
from app.infrastructure.queue.producer import CeleryScanJobQueue
from app.infrastructure.scanner.analyzer import StaticPackageAnalyzer
from app.infrastructure.scanner.extractor import SafeExtractor
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _build_scan_use_case() -> ScanPackageUseCase:
    settings = get_settings()
    return ScanPackageUseCase(
        repository_unit_of_work_factory=SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal),
        package_registry=NpmRegistryClient(
            base_url=settings.npm_registry_base_url,
            timeout_seconds=settings.npm_registry_timeout_seconds,
        ),
        tarball_downloader=TarballDownloader(
            timeout_seconds=settings.tarball_download_timeout_seconds,
            max_bytes=settings.tarball_max_bytes,
        ),
        extractor=SafeExtractor(
            max_members=settings.tarball_max_members,
            max_total_uncompressed_bytes=settings.tarball_max_uncompressed_bytes,
            max_file_bytes=settings.tarball_max_file_bytes,
            max_path_depth=settings.tarball_max_path_depth,
        ),
        analyzer=StaticPackageAnalyzer(
            max_files=settings.scanner_max_files,
            max_text_file_bytes=settings.scanner_max_text_file_bytes,
            package_json_max_bytes=settings.package_json_max_bytes,
        ),
    )


def _build_top_packages_use_case() -> EnqueueTopPackagesBatchUseCase:
    settings = get_settings()
    repository_uow_factory = SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal)
    return EnqueueTopPackagesBatchUseCase(
        package_list_source=MeyondTopPackagesSource(
            source_url=settings.top_packages_source_url,
            timeout_seconds=settings.top_packages_source_timeout_seconds,
        ),
        enqueue_scan_use_case=EnqueueScanUseCase(CeleryScanJobQueue(), repository_uow_factory),
    )


async def _mark_queue_job_running(task_id: str, package_name: str, reason: str) -> None:
    repository_uow_factory = SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal)
    async with repository_uow_factory() as repository:
        try:
            await repository.mark_queue_job_running(task_id=task_id)
        except ValueError:
            await repository.create_queue_job(
                task_id=task_id,
                job_type="scan_package",
                package_name=package_name,
                reason=reason,
            )
            await repository.mark_queue_job_running(task_id=task_id)


async def _mark_queue_job_completed(task_id: str) -> None:
    repository_uow_factory = SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal)
    async with repository_uow_factory() as repository:
        await repository.mark_queue_job_completed(task_id=task_id)


async def _mark_queue_job_failed(task_id: str, error_message: str) -> None:
    repository_uow_factory = SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal)
    async with repository_uow_factory() as repository:
        await repository.mark_queue_job_failed(task_id=task_id, error_message=error_message)


async def _mark_batch_job_running(task_id: str, reason: str) -> None:
    repository_uow_factory = SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal)
    async with repository_uow_factory() as repository:
        try:
            await repository.mark_queue_job_running(task_id=task_id)
        except ValueError:
            await repository.create_queue_job(
                task_id=task_id,
                job_type="top_packages_batch",
                package_name=None,
                reason=reason,
            )
            await repository.mark_queue_job_running(task_id=task_id)


@celery_app.task(
    name="app.worker.tasks.scan_package",
    bind=True,
    autoretry_for=(NpmRegistryTimeoutError, TarballDownloadError),
    dont_autoretry_for=(
        NpmPackageNotFoundError,
        NpmRegistryMalformedResponseError,
        ScannerLimitExceededError,
        TarballExtractError,
        TarballIntegrityError,
        TarballSizeLimitExceededError,
    ),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def scan_package(self, package_name: str, reason: str = "manual", task_id: str | None = None) -> dict[str, str]:
    queue_task_id = task_id or getattr(self.request, "id", None) or uuid4().hex
    logger.info(
        "scan_job_received",
        extra={
            "task_id": queue_task_id,
            "package_name": package_name,
            "job_reason": reason,
        },
    )

    asyncio.run(_mark_queue_job_running(queue_task_id, package_name, reason))
    try:
        asyncio.run(_build_scan_use_case().execute(package_name=package_name, reason=reason))
    except Exception as exc:
        asyncio.run(_mark_queue_job_failed(queue_task_id, str(exc) or exc.__class__.__name__))
        raise
    asyncio.run(_mark_queue_job_completed(queue_task_id))

    logger.info(
        "scan_job_completed",
        extra={"task_id": queue_task_id, "package_name": package_name, "job_reason": reason},
    )
    return {"task_id": queue_task_id, "package_name": package_name, "reason": reason, "status": "completed"}


@celery_app.task(name="app.worker.tasks.enqueue_top_packages")
def enqueue_top_packages(limit: int, reason: str = "manual_batch", task_id: str | None = None) -> dict[str, int | str]:
    queue_task_id = task_id or "batch-" + uuid4().hex
    logger.info("top_package_batch_received", extra={"task_id": queue_task_id, "limit": limit, "reason": reason})
    asyncio.run(_mark_batch_job_running(queue_task_id, reason))
    try:
        result = asyncio.run(_build_top_packages_use_case().execute(limit=limit, reason=reason))
    except Exception as exc:
        asyncio.run(_mark_queue_job_failed(queue_task_id, str(exc) or exc.__class__.__name__))
        raise
    asyncio.run(_mark_queue_job_completed(queue_task_id))
    logger.info(
        "top_package_batch_completed",
        extra={
            "task_id": queue_task_id,
            "limit": limit,
            "reason": reason,
            "requested": result.requested,
            "enqueued": result.enqueued,
            "skipped": result.skipped,
        },
    )
    return {
        "task_id": queue_task_id,
        "status": "completed",
        "requested": result.requested,
        "enqueued": result.enqueued,
        "skipped": result.skipped,
    }
