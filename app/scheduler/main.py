import asyncio
import logging
import signal

from app.application.use_cases.enqueue_scan import EnqueueScanUseCase
from app.application.use_cases.monitor_updates import MonitorUpdatesUseCase, PackageScanState
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.db.repositories import SqlAlchemyPackageRepository
from app.infrastructure.db.session import SessionLocal, check_database_connection
from app.infrastructure.db.unit_of_work import SqlAlchemyRepositoryUnitOfWorkFactory
from app.infrastructure.npm.registry_client import NpmRegistryClient
from app.infrastructure.package_list.meyond_top_packages_source import MeyondTopPackagesSource
from app.infrastructure.queue.producer import CeleryScanJobQueue

logger = logging.getLogger(__name__)


def _build_monitor_use_case() -> MonitorUpdatesUseCase:
    settings = get_settings()

    async def load_package_scan_state(package_name: str) -> PackageScanState:
        async with SessionLocal() as session:
            repository = SqlAlchemyPackageRepository(session)
            package = await repository.get_by_name(package_name)
            if package is None:
                return PackageScanState(package_id=None, latest_scanned_version=None)
            return PackageScanState(package_id=package.id, latest_scanned_version=package.latest_scanned_version)

    async def has_running_scan(package_id: int) -> bool:
        async with SessionLocal() as session:
            repository = SqlAlchemyPackageRepository(session)
            return await repository.has_running_scan(package_id)

    return MonitorUpdatesUseCase(
        package_list_source=MeyondTopPackagesSource(
            source_url=settings.top_packages_source_url,
            timeout_seconds=settings.top_packages_source_timeout_seconds,
        ),
        package_registry=NpmRegistryClient(
            base_url=settings.npm_registry_base_url,
            timeout_seconds=settings.npm_registry_timeout_seconds,
        ),
        enqueue_scan_use_case=EnqueueScanUseCase(
            CeleryScanJobQueue(),
            SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal),
        ),
        load_package_scan_state=load_package_scan_state,
        has_running_scan=has_running_scan,
        top_package_limit=settings.top_package_limit,
        metadata_concurrency=settings.scheduler_metadata_concurrency,
        skip_running_scans=settings.scheduler_skip_running_scans,
    )


async def run_scheduler() -> None:
    shutdown_requested = asyncio.Event()

    settings = get_settings()
    configure_logging(settings)
    monitor_use_case = _build_monitor_use_case()

    def request_shutdown(signum: int, _: object) -> None:
        logger.info(
            "scheduler_shutdown_requested",
            extra={"service": settings.service_name, "signal": signum},
        )
        shutdown_requested.set()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    await check_database_connection(settings.database_url)
    logger.info("scheduler_started", extra={"service": settings.service_name})

    while not shutdown_requested.is_set():
        try:
            result = await monitor_use_case.execute_once()
            logger.info(
                "scheduler_tick_completed",
                extra={
                    "service": settings.service_name,
                    "checked_count": result.checked_count,
                    "enqueued_new_count": result.enqueued_new_count,
                    "enqueued_updated_count": result.enqueued_updated_count,
                    "unchanged_count": result.unchanged_count,
                    "skipped_running_count": result.skipped_running_count,
                    "failed_count": result.failed_count,
                },
            )
        except Exception:
            logger.exception("scheduler_tick_failed", extra={"service": settings.service_name})

        try:
            await asyncio.wait_for(shutdown_requested.wait(), timeout=settings.scheduler_interval_seconds)
        except TimeoutError:
            continue

    logger.info("scheduler_stopped", extra={"service": settings.service_name})


def run() -> None:
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    run()
