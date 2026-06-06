from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


@dataclass(frozen=True)
class PackageListFilters:
    risk_level: str | None = None
    name_query: str | None = None


@dataclass(frozen=True)
class ScanResultFilters:
    status: str | None = None
    risk_level: str | None = None
    package_name: str | None = None


@dataclass(frozen=True)
class FindingFilters:
    severity: str | None = None
    finding_type: str | None = None
    package_name: str | None = None


@dataclass(frozen=True)
class PackageVersionMetadata:
    published_at: datetime | None = None
    tarball_url: str | None = None
    integrity: str | None = None
    unpacked_size: int | None = None
    file_count: int | None = None
    package_json: dict[str, Any] = field(default_factory=dict)
    dependencies: dict[str, Any] = field(default_factory=dict)
    scripts: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FindingCreate:
    finding_type: str
    severity: str
    category: str
    description: str
    file_path: str | None = None
    evidence: str | None = None


@dataclass(frozen=True)
class PackageListItem:
    id: int
    name: str
    latest_scanned_version: str | None
    last_scanned_at: datetime | None
    latest_scan_risk_level: str | None


@dataclass(frozen=True)
class ScanResultRead:
    id: int
    package_id: int
    package_name: str
    latest_version: str | None
    previous_version: str | None
    status: str
    score: int | None
    risk_level: str
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


@dataclass(frozen=True)
class FindingRead:
    id: int
    scan_result_id: int
    package_id: int
    package_name: str
    finding_type: str
    severity: str
    category: str
    file_path: str | None
    description: str
    evidence: str | None
    created_at: datetime


@dataclass(frozen=True)
class PackageDetail:
    id: int
    name: str
    latest_scanned_version: str | None
    last_scanned_at: datetime | None
    latest_scan: ScanResultRead | None
    versions_count: int
    findings_count: int


@dataclass(frozen=True)
class PackageVersionRead:
    id: int
    package_id: int
    package_name: str
    version: str
    published_at: datetime | None
    tarball_url: str | None
    integrity: str | None
    unpacked_size: int | None
    file_count: int | None
    package_json: dict[str, Any]
    dependencies: dict[str, Any]
    scripts: dict[str, Any]
    created_at: datetime


class PackageRepository(Protocol):
    async def get_by_name(self, name: str) -> object | None:
        ...

    async def upsert_package(self, name: str) -> object:
        ...

    async def upsert_package_version(
        self,
        package_id: int,
        version: str,
        metadata: PackageVersionMetadata,
    ) -> object:
        ...

    async def create_scan_result(
        self,
        package_id: int,
        latest_version: str | None,
        previous_version: str | None,
        *,
        status: str = "running",
    ) -> object:
        ...

    async def claim_next_queued_scan(self, package_id: int) -> object | None:
        ...

    async def set_scan_versions(
        self,
        scan_result_id: int,
        latest_version: str,
        previous_version: str | None,
    ) -> None:
        ...

    async def mark_scan_completed(self, scan_result_id: int, score: int, risk_level: str) -> None:
        ...

    async def mark_scan_failed(self, scan_result_id: int, error_message: str) -> None:
        ...

    async def add_findings(self, scan_result_id: int, findings: list[FindingCreate]) -> None:
        ...

    async def replace_findings(self, scan_result_id: int, findings: list[FindingCreate]) -> None:
        ...

    async def mark_package_scanned(self, package_id: int, latest_scanned_version: str) -> None:
        ...

    async def has_running_scan(self, package_id: int) -> bool:
        ...

    async def create_queue_job(
        self,
        *,
        task_id: str,
        job_type: str,
        package_name: str | None,
        reason: str,
    ) -> None:
        ...

    async def mark_queue_job_running(self, *, task_id: str) -> None:
        ...

    async def mark_queue_job_completed(self, *, task_id: str) -> None:
        ...

    async def mark_queue_job_failed(self, *, task_id: str, error_message: str) -> None:
        ...

    async def list_packages(
        self,
        filters: PackageListFilters,
        pagination: Pagination,
    ) -> tuple[list[PackageListItem], int]:
        ...

    async def get_package_detail(self, name: str) -> PackageDetail | None:
        ...

    async def list_package_versions(
        self,
        package_name: str,
        pagination: Pagination,
    ) -> tuple[list[PackageVersionRead], int]:
        ...

    async def list_scan_results(
        self,
        filters: ScanResultFilters,
        pagination: Pagination,
    ) -> tuple[list[ScanResultRead], int]:
        ...

    async def list_findings(
        self,
        filters: FindingFilters,
        pagination: Pagination,
    ) -> tuple[list[FindingRead], int]:
        ...
