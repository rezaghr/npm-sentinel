from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str


class EnqueueScanResponse(BaseModel):
    status: str
    package_name: str
    reason: str


class ScanBatchRequest(BaseModel):
    source: Literal["top_packages"] = "top_packages"
    limit: int = Field(default=1000, ge=1, le=1000)
    reason: str = Field(default="manual_batch", min_length=1, max_length=64)


class ScanBatchResponse(BaseModel):
    status: str
    source: str
    requested: int
    enqueued: int
    skipped: int
    reason: str


class ScanResultResponse(BaseModel):
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


class PackageListItemResponse(BaseModel):
    id: int
    name: str
    latest_scanned_version: str | None
    last_scanned_at: datetime | None
    latest_scan_risk_level: str | None


class PackageDetailResponse(BaseModel):
    id: int
    name: str
    latest_scanned_version: str | None
    last_scanned_at: datetime | None
    latest_scan: ScanResultResponse | None
    versions_count: int
    findings_count: int


class PackageVersionResponse(BaseModel):
    id: int
    package_id: int
    package_name: str
    version: str
    published_at: datetime | None
    tarball_url: str | None
    integrity: str | None
    unpacked_size: int | None
    file_count: int | None
    package_json: dict
    dependencies: dict
    scripts: dict
    created_at: datetime


class FindingResponse(BaseModel):
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


class PackageListResponse(BaseModel):
    items: list[PackageListItemResponse]
    total: int
    limit: int
    offset: int


class PackageVersionListResponse(BaseModel):
    items: list[PackageVersionResponse]
    total: int
    limit: int
    offset: int


class ScanListResponse(BaseModel):
    items: list[ScanResultResponse]
    total: int
    limit: int
    offset: int


class FindingListResponse(BaseModel):
    items: list[FindingResponse]
    total: int
    limit: int
    offset: int
