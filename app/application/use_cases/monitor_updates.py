from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from app.application.ports.package_list_source import PackageListSource
from app.application.ports.package_registry import PackageRegistry
from app.application.use_cases.enqueue_scan import EnqueueScanUseCase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PackageMonitorError:
    package_name: str
    error: str


@dataclass
class MonitorUpdatesResult:
    checked_count: int = 0
    enqueued_new_count: int = 0
    enqueued_updated_count: int = 0
    unchanged_count: int = 0
    skipped_running_count: int = 0
    failed_count: int = 0
    errors: list[PackageMonitorError] = field(default_factory=list)


@dataclass(frozen=True)
class PackageScanState:
    package_id: int | None
    latest_scanned_version: str | None


class MonitorUpdatesUseCase:
    def __init__(
        self,
        *,
        package_list_source: PackageListSource,
        package_registry: PackageRegistry,
        enqueue_scan_use_case: EnqueueScanUseCase,
        load_package_scan_state: Callable[[str], Awaitable[PackageScanState]],
        has_running_scan: Callable[[int], Awaitable[bool]],
        top_package_limit: int,
        metadata_concurrency: int,
        skip_running_scans: bool = False,
    ) -> None:
        self._package_list_source = package_list_source
        self._package_registry = package_registry
        self._enqueue_scan_use_case = enqueue_scan_use_case
        self._load_package_scan_state = load_package_scan_state
        self._has_running_scan = has_running_scan
        self._top_package_limit = top_package_limit
        self._metadata_concurrency = metadata_concurrency
        self._skip_running_scans = skip_running_scans

    async def execute_once(self) -> MonitorUpdatesResult:
        package_names = await self._package_list_source.load_package_names(limit=self._top_package_limit)
        result = MonitorUpdatesResult()
        semaphore = asyncio.Semaphore(self._metadata_concurrency)

        tasks = [
            asyncio.create_task(self._process_package(package_name, semaphore, result))
            for package_name in package_names
        ]
        if tasks:
            await asyncio.gather(*tasks)

        return result

    async def _process_package(
        self,
        package_name: str,
        semaphore: asyncio.Semaphore,
        result: MonitorUpdatesResult,
    ) -> None:
        try:
            async with semaphore:
                metadata = await self._package_registry.fetch_metadata(package_name)
        except Exception as exc:
            self._record_failure(result, package_name, exc)
            return

        result.checked_count += 1

        try:
            state = await self._load_package_scan_state(metadata.package_name)
            update_type = _classify_update(
                latest_scanned_version=state.latest_scanned_version,
                registry_latest_version=metadata.latest_version.version,
            )

            if update_type == "unchanged":
                result.unchanged_count += 1
                return

            if self._skip_running_scans and state.package_id is not None:
                if await self._has_running_scan(state.package_id):
                    result.skipped_running_count += 1
                    return

            await self._enqueue_scan_use_case.execute(metadata.package_name, reason="scheduler")

            logger.info(
                "update_detected",
                extra={
                    "package_name": metadata.package_name,
                    "update_type": update_type,
                    "latest_version": metadata.latest_version.version,
                    "latest_scanned_version": state.latest_scanned_version,
                },
            )

            if update_type == "new":
                result.enqueued_new_count += 1
            else:
                result.enqueued_updated_count += 1
        except Exception as exc:
            self._record_failure(result, package_name, exc)

    @staticmethod
    def _record_failure(result: MonitorUpdatesResult, package_name: str, exc: Exception) -> None:
        result.failed_count += 1
        error_message = str(exc) or exc.__class__.__name__
        result.errors.append(
            PackageMonitorError(
                package_name=package_name,
                error=error_message,
            )
        )
        logger.warning(
            "package_monitor_failed",
            extra={
                "package_name": package_name,
                "error_type": exc.__class__.__name__,
                "error_message": error_message[:500],
            },
        )


def _classify_update(*, latest_scanned_version: str | None, registry_latest_version: str) -> str:
    if latest_scanned_version is None:
        return "new"
    if latest_scanned_version != registry_latest_version:
        return "updated"
    return "unchanged"
