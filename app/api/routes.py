from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    EnqueueScanResponse,
    FindingListResponse,
    FindingResponse,
    HealthResponse,
    PackageDetailResponse,
    PackageListItemResponse,
    PackageListResponse,
    PackageVersionListResponse,
    PackageVersionResponse,
    ScanBatchRequest,
    ScanBatchResponse,
    ScanListResponse,
    ScanResultResponse,
)
from app.application.ports.queue import ScanJobQueue
from app.application.ports.unit_of_work import RepositoryUnitOfWorkFactory
from app.application.use_cases.enqueue_scan import EnqueueScanUseCase
from app.application.use_cases.enqueue_top_packages_batch import EnqueueTopPackagesBatchUseCase
from app.application.use_cases.get_package_details import GetPackageDetailsUseCase
from app.application.use_cases.list_findings import ListFindingsUseCase
from app.application.use_cases.list_packages import ListPackagesUseCase
from app.application.use_cases.list_package_versions import ListPackageVersionsUseCase
from app.application.use_cases.list_scans import ListScansUseCase
from app.core.config import get_settings
from app.core.exceptions import QueuePublishError
from app.infrastructure.db.repositories import SqlAlchemyPackageRepository
from app.infrastructure.package_list.meyond_top_packages_source import MeyondTopPackagesSource
from app.infrastructure.db.session import get_db_session
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.unit_of_work import SqlAlchemyRepositoryUnitOfWorkFactory
from app.infrastructure.queue.producer import CeleryScanJobQueue
from app.application.ports.package_list_source import PackageListSource

router = APIRouter()


def get_scan_job_queue() -> ScanJobQueue:
    return CeleryScanJobQueue()


def get_top_packages_source() -> PackageListSource:
    settings = get_settings()
    return MeyondTopPackagesSource(
        source_url=settings.top_packages_source_url,
        timeout_seconds=settings.top_packages_source_timeout_seconds,
    )


def get_repository_uow_factory() -> RepositoryUnitOfWorkFactory:
    return SqlAlchemyRepositoryUnitOfWorkFactory(SessionLocal)


@router.get("/health")
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.service_name)


@router.post(
    "/scan-batches",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScanBatchResponse,
)
async def enqueue_scan_batch(
    payload: ScanBatchRequest,
    queue: ScanJobQueue = Depends(get_scan_job_queue),
    package_list_source: PackageListSource = Depends(get_top_packages_source),
    repository_uow_factory: RepositoryUnitOfWorkFactory = Depends(get_repository_uow_factory),
) -> ScanBatchResponse:
    if payload.source != "top_packages":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported scan source")

    normalized_reason = payload.reason.strip() or "manual_batch"
    use_case = EnqueueTopPackagesBatchUseCase(
        package_list_source=package_list_source,
        enqueue_scan_use_case=EnqueueScanUseCase(queue, repository_uow_factory),
    )
    try:
        result = await use_case.execute(limit=payload.limit, reason=normalized_reason)
    except QueuePublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="scan queue unavailable",
        ) from exc

    return ScanBatchResponse(
        status="queued",
        source=payload.source,
        requested=result.requested,
        enqueued=result.enqueued,
        skipped=result.skipped,
        reason=normalized_reason,
    )


@router.post(
    "/scans/top-packages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ScanBatchResponse,
)
async def enqueue_top_packages_compat(
    limit: int | None = Query(default=None, ge=1, le=1000),
    reason: str = "manual_batch",
    queue: ScanJobQueue = Depends(get_scan_job_queue),
    package_list_source: PackageListSource = Depends(get_top_packages_source),
    repository_uow_factory: RepositoryUnitOfWorkFactory = Depends(get_repository_uow_factory),
) -> ScanBatchResponse:
    payload = ScanBatchRequest(limit=limit or get_settings().top_package_limit, reason=reason)
    return await enqueue_scan_batch(payload, queue, package_list_source, repository_uow_factory)


@router.post(
    "/packages/{package_name:path}/scans",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EnqueueScanResponse,
)
@router.post(
    "/scans/{package_name}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EnqueueScanResponse,
)
async def enqueue_scan(
    package_name: str,
    reason: str = "manual",
    queue: ScanJobQueue = Depends(get_scan_job_queue),
    repository_uow_factory: RepositoryUnitOfWorkFactory = Depends(get_repository_uow_factory),
) -> EnqueueScanResponse:
    normalized_package_name = package_name.strip()
    normalized_reason = reason.strip() or "manual"
    use_case = EnqueueScanUseCase(queue, repository_uow_factory)

    try:
        await use_case.execute(normalized_package_name, normalized_reason)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except QueuePublishError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="scan queue unavailable",
        ) from exc

    return EnqueueScanResponse(
        status="queued",
        package_name=normalized_package_name,
        reason=normalized_reason,
    )


@router.get("/packages", response_model=PackageListResponse)
async def list_packages(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    risk_level: Literal["low", "medium", "high", "unknown"] | None = None,
    name: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> PackageListResponse:
    repository = SqlAlchemyPackageRepository(session)
    use_case = ListPackagesUseCase(repository)
    items, total = await use_case.execute(
        limit=limit,
        offset=offset,
        risk_level=risk_level,
        name_query=name,
    )
    return PackageListResponse(
        items=[
            PackageListItemResponse(
                id=item.id,
                name=item.name,
                latest_scanned_version=item.latest_scanned_version,
                last_scanned_at=item.last_scanned_at,
                latest_scan_risk_level=item.latest_scan_risk_level,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/package-versions/{package_name:path}", response_model=PackageVersionListResponse)
async def list_package_versions(
    package_name: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> PackageVersionListResponse:
    repository = SqlAlchemyPackageRepository(session)
    use_case = ListPackageVersionsUseCase(repository)
    items, total = await use_case.execute(
        package_name=package_name.strip(),
        limit=limit,
        offset=offset,
    )
    if total == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package not found")

    return PackageVersionListResponse(
        items=[
            PackageVersionResponse(
                id=item.id,
                package_id=item.package_id,
                package_name=item.package_name,
                version=item.version,
                published_at=item.published_at,
                tarball_url=item.tarball_url,
                integrity=item.integrity,
                unpacked_size=item.unpacked_size,
                file_count=item.file_count,
                package_json=item.package_json,
                dependencies=item.dependencies,
                scripts=item.scripts,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/packages/{package_name:path}", response_model=PackageDetailResponse)
async def get_package_detail(
    package_name: str,
    session: AsyncSession = Depends(get_db_session),
) -> PackageDetailResponse:
    repository = SqlAlchemyPackageRepository(session)
    use_case = GetPackageDetailsUseCase(repository)
    detail = await use_case.execute(package_name.strip())
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="package not found")

    latest_scan = (
        ScanResultResponse(
            id=detail.latest_scan.id,
            package_id=detail.latest_scan.package_id,
            package_name=detail.latest_scan.package_name,
            latest_version=detail.latest_scan.latest_version,
            previous_version=detail.latest_scan.previous_version,
            status=detail.latest_scan.status,
            score=detail.latest_scan.score,
            risk_level=detail.latest_scan.risk_level,
            error_message=detail.latest_scan.error_message,
            started_at=detail.latest_scan.started_at,
            finished_at=detail.latest_scan.finished_at,
            created_at=detail.latest_scan.created_at,
        )
        if detail.latest_scan is not None
        else None
    )

    return PackageDetailResponse(
        id=detail.id,
        name=detail.name,
        latest_scanned_version=detail.latest_scanned_version,
        last_scanned_at=detail.last_scanned_at,
        latest_scan=latest_scan,
        versions_count=detail.versions_count,
        findings_count=detail.findings_count,
    )


@router.get("/scans", response_model=ScanListResponse)
async def list_scans(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Literal["queued", "running", "completed", "failed"] | None = Query(default=None, alias="status"),
    risk_level: Literal["low", "medium", "high", "unknown"] | None = None,
    package_name: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> ScanListResponse:
    repository = SqlAlchemyPackageRepository(session)
    use_case = ListScansUseCase(repository)
    items, total = await use_case.execute(
        limit=limit,
        offset=offset,
        status=status_filter,
        risk_level=risk_level,
        package_name=package_name,
    )
    return ScanListResponse(
        items=[
            ScanResultResponse(
                id=item.id,
                package_id=item.package_id,
                package_name=item.package_name,
                latest_version=item.latest_version,
                previous_version=item.previous_version,
                status=item.status,
                score=item.score,
                risk_level=item.risk_level,
                error_message=item.error_message,
                started_at=item.started_at,
                finished_at=item.finished_at,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/findings", response_model=FindingListResponse)
async def list_findings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    severity: Literal["low", "medium", "high", "critical"] | None = None,
    type_filter: str | None = Query(default=None, alias="type"),
    package_name: str | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> FindingListResponse:
    repository = SqlAlchemyPackageRepository(session)
    use_case = ListFindingsUseCase(repository)
    items, total = await use_case.execute(
        limit=limit,
        offset=offset,
        severity=severity,
        finding_type=type_filter,
        package_name=package_name,
    )
    return FindingListResponse(
        items=[
            FindingResponse(
                id=item.id,
                scan_result_id=item.scan_result_id,
                package_id=item.package_id,
                package_name=item.package_name,
                finding_type=item.finding_type,
                severity=item.severity,
                category=item.category,
                file_path=item.file_path,
                description=item.description,
                evidence=item.evidence,
                created_at=item.created_at,
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
