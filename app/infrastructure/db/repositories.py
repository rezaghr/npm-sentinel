from datetime import UTC, datetime

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.package_repository import (
    FindingCreate,
    FindingFilters,
    FindingRead,
    PackageDetail,
    PackageListFilters,
    PackageListItem,
    PackageVersionRead,
    PackageVersionMetadata,
    Pagination,
    ScanResultFilters,
    ScanResultRead,
)
from app.infrastructure.db.models import (
    FindingModel,
    PackageModel,
    PackageVersionModel,
    QueueJobModel,
    QueueJobStatus,
    RiskLevel,
    ScanResultModel,
    ScanStatus,
)


class SqlAlchemyPackageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name(self, name: str) -> PackageModel | None:
        result = await self._session.execute(select(PackageModel).where(PackageModel.name == name))
        return result.scalar_one_or_none()

    async def upsert_package(self, name: str) -> PackageModel:
        statement = (
            insert(PackageModel)
            .values(name=name)
            .on_conflict_do_update(
                index_elements=[PackageModel.name],
                set_={"updated_at": func.now()},
            )
            .returning(PackageModel)
        )
        result = await self._session.execute(statement, execution_options={"populate_existing": True})
        package = result.scalar_one()
        await self._session.flush()
        return package

    async def upsert_package_version(
        self,
        package_id: int,
        version: str,
        metadata: PackageVersionMetadata,
    ) -> PackageVersionModel:
        values = {
            "package_id": package_id,
            "version": version,
            "published_at": metadata.published_at,
            "tarball_url": metadata.tarball_url,
            "integrity": metadata.integrity,
            "unpacked_size": metadata.unpacked_size,
            "file_count": metadata.file_count,
            "package_json": metadata.package_json,
            "dependencies": metadata.dependencies,
            "scripts": metadata.scripts,
        }
        statement = (
            insert(PackageVersionModel)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_package_versions_package_id_version",
                set_={
                    "published_at": metadata.published_at,
                    "tarball_url": metadata.tarball_url,
                    "integrity": metadata.integrity,
                    "unpacked_size": metadata.unpacked_size,
                    "file_count": metadata.file_count,
                    "package_json": metadata.package_json,
                    "dependencies": metadata.dependencies,
                    "scripts": metadata.scripts,
                },
            )
            .returning(PackageVersionModel)
        )
        result = await self._session.execute(statement, execution_options={"populate_existing": True})
        package_version = result.scalar_one()
        await self._session.flush()
        return package_version

    async def create_scan_result(
        self,
        package_id: int,
        latest_version: str | None,
        previous_version: str | None,
        *,
        status: str = ScanStatus.RUNNING.value,
    ) -> ScanResultModel:
        scan_result = ScanResultModel(
            package_id=package_id,
            latest_version=latest_version,
            previous_version=previous_version,
            status=status,
            risk_level=RiskLevel.UNKNOWN.value,
            score=None,
            error_message=None,
            finished_at=None,
        )
        self._session.add(scan_result)
        await self._session.flush()
        return scan_result

    async def claim_next_queued_scan(self, package_id: int) -> ScanResultModel | None:
        result = await self._session.execute(
            select(ScanResultModel)
            .where(
                ScanResultModel.package_id == package_id,
                ScanResultModel.status == ScanStatus.QUEUED.value,
            )
            .order_by(ScanResultModel.created_at.asc(), ScanResultModel.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        scan_result = result.scalar_one_or_none()
        if scan_result is None:
            return None

        scan_result.status = ScanStatus.RUNNING.value
        scan_result.started_at = datetime.now(UTC)
        scan_result.finished_at = None
        scan_result.error_message = None
        await self._session.flush()
        return scan_result

    async def set_scan_versions(
        self,
        scan_result_id: int,
        latest_version: str,
        previous_version: str | None,
    ) -> None:
        scan_result = await self._session.get(ScanResultModel, scan_result_id)
        if scan_result is None:
            raise ValueError(f"scan result not found: {scan_result_id}")
        if scan_result.status != ScanStatus.RUNNING.value:
            return

        scan_result.latest_version = latest_version
        scan_result.previous_version = previous_version
        await self._session.flush()

    async def mark_scan_completed(self, scan_result_id: int, score: int, risk_level: str) -> None:
        result = await self._session.execute(
            update(ScanResultModel)
            .where(
                ScanResultModel.id == scan_result_id,
                ScanResultModel.status == ScanStatus.RUNNING.value,
            )
            .values(
                status=ScanStatus.COMPLETED.value,
                score=score,
                risk_level=risk_level,
                error_message=None,
                finished_at=datetime.now(UTC),
            )
        )
        if result.rowcount == 0 and await self._session.get(ScanResultModel, scan_result_id) is None:
            raise ValueError(f"scan result not found: {scan_result_id}")
        await self._session.flush()

    async def mark_scan_failed(self, scan_result_id: int, error_message: str) -> None:
        result = await self._session.execute(
            update(ScanResultModel)
            .where(
                ScanResultModel.id == scan_result_id,
                ScanResultModel.status == ScanStatus.RUNNING.value,
            )
            .values(
                status=ScanStatus.FAILED.value,
                error_message=error_message,
                finished_at=datetime.now(UTC),
            )
        )
        if result.rowcount == 0 and await self._session.get(ScanResultModel, scan_result_id) is None:
            raise ValueError(f"scan result not found: {scan_result_id}")
        await self._session.flush()

    async def add_findings(self, scan_result_id: int, findings: list[FindingCreate]) -> None:
        self._session.add_all(
            FindingModel(
                scan_result_id=scan_result_id,
                finding_type=finding.finding_type,
                severity=finding.severity,
                category=finding.category,
                file_path=finding.file_path,
                description=finding.description,
                evidence=finding.evidence,
            )
            for finding in findings
        )
        await self._session.flush()

    async def replace_findings(self, scan_result_id: int, findings: list[FindingCreate]) -> None:
        await self._session.execute(delete(FindingModel).where(FindingModel.scan_result_id == scan_result_id))
        await self.add_findings(scan_result_id, findings)

    async def mark_package_scanned(self, package_id: int, latest_scanned_version: str) -> None:
        package = await self._session.get(PackageModel, package_id)
        if package is None:
            raise ValueError(f"package not found: {package_id}")

        package.latest_scanned_version = latest_scanned_version
        package.last_scanned_at = datetime.now(UTC)
        await self._session.flush()

    async def has_running_scan(self, package_id: int) -> bool:
        result = await self._session.execute(
            select(ScanResultModel.id)
            .where(
                ScanResultModel.package_id == package_id,
                ScanResultModel.status == ScanStatus.RUNNING.value,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def create_queue_job(
        self,
        *,
        task_id: str,
        job_type: str,
        package_name: str | None,
        reason: str,
    ) -> None:
        statement = (
            insert(QueueJobModel)
            .values(
                task_id=task_id,
                job_type=job_type,
                package_name=package_name,
                reason=reason,
                status=QueueJobStatus.QUEUED.value,
                error_message=None,
                started_at=None,
                finished_at=None,
            )
            .on_conflict_do_nothing(index_elements=[QueueJobModel.task_id])
        )
        await self._session.execute(statement)
        await self._session.flush()

    async def mark_queue_job_running(self, *, task_id: str) -> None:
        result = await self._session.execute(
            update(QueueJobModel)
            .where(
                QueueJobModel.task_id == task_id,
                QueueJobModel.status.in_([QueueJobStatus.QUEUED.value, QueueJobStatus.FAILED.value]),
            )
            .values(
                status=QueueJobStatus.RUNNING.value,
                started_at=datetime.now(UTC),
                error_message=None,
                finished_at=None,
            )
        )
        if result.rowcount == 0 and await self._session.get(QueueJobModel, task_id) is None:
            raise ValueError(f"queue job not found: {task_id}")
        await self._session.flush()

    async def mark_queue_job_completed(self, *, task_id: str) -> None:
        result = await self._session.execute(
            update(QueueJobModel)
            .where(
                QueueJobModel.task_id == task_id,
                QueueJobModel.status.in_([QueueJobStatus.QUEUED.value, QueueJobStatus.RUNNING.value]),
            )
            .values(
                status=QueueJobStatus.COMPLETED.value,
                finished_at=datetime.now(UTC),
                error_message=None,
            )
        )
        if result.rowcount == 0 and await self._session.get(QueueJobModel, task_id) is None:
            raise ValueError(f"queue job not found: {task_id}")
        await self._session.flush()

    async def mark_queue_job_failed(self, *, task_id: str, error_message: str) -> None:
        result = await self._session.execute(
            update(QueueJobModel)
            .where(
                QueueJobModel.task_id == task_id,
                QueueJobModel.status.in_([QueueJobStatus.QUEUED.value, QueueJobStatus.RUNNING.value]),
            )
            .values(
                status=QueueJobStatus.FAILED.value,
                finished_at=datetime.now(UTC),
                error_message=error_message,
            )
        )
        if result.rowcount == 0 and await self._session.get(QueueJobModel, task_id) is None:
            raise ValueError(f"queue job not found: {task_id}")
        await self._session.flush()

    async def list_packages(
        self,
        filters: PackageListFilters,
        pagination: Pagination,
    ) -> tuple[list[PackageListItem], int]:
        latest_scan = self._latest_scan_subquery()
        latest_completed_scan = self._latest_scan_subquery(completed_only=True)

        count_query = select(func.count()).select_from(PackageModel)
        query = (
            select(
                PackageModel.id,
                PackageModel.name,
                PackageModel.latest_scanned_version,
                PackageModel.last_scanned_at,
                latest_scan.c.risk_level.label("latest_scan_risk_level"),
            )
            .outerjoin(latest_scan, latest_scan.c.package_id == PackageModel.id)
            .order_by(PackageModel.last_scanned_at.desc().nulls_last(), PackageModel.name.asc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )

        if filters.name_query:
            like_pattern = f"%{filters.name_query}%"
            count_query = count_query.where(PackageModel.name.ilike(like_pattern))
            query = query.where(PackageModel.name.ilike(like_pattern))

        if filters.risk_level:
            query = query.join(latest_completed_scan, latest_completed_scan.c.package_id == PackageModel.id)
            query = query.where(latest_completed_scan.c.risk_level == filters.risk_level)
            count_query = count_query.where(
                PackageModel.id.in_(
                    select(latest_completed_scan.c.package_id).where(
                        latest_completed_scan.c.risk_level == filters.risk_level
                    )
                )
            )

        rows = (await self._session.execute(query)).all()
        total = (await self._session.execute(count_query)).scalar_one()
        items = [
            PackageListItem(
                id=row.id,
                name=row.name,
                latest_scanned_version=row.latest_scanned_version,
                last_scanned_at=row.last_scanned_at,
                latest_scan_risk_level=row.latest_scan_risk_level,
            )
            for row in rows
        ]
        return items, total

    async def get_package_detail(self, name: str) -> PackageDetail | None:
        package = await self.get_by_name(name)
        if package is None:
            return None

        latest_scan = self._latest_scan_subquery()
        latest_scan_query = select(latest_scan).where(latest_scan.c.package_id == package.id)
        latest_scan_row = (await self._session.execute(latest_scan_query)).mappings().one_or_none()

        versions_count_query = select(func.count()).select_from(PackageVersionModel).where(
            PackageVersionModel.package_id == package.id
        )
        findings_count_query = (
            select(func.count())
            .select_from(FindingModel)
            .join(ScanResultModel, FindingModel.scan_result_id == ScanResultModel.id)
            .where(ScanResultModel.package_id == package.id)
        )

        versions_count = (await self._session.execute(versions_count_query)).scalar_one()
        findings_count = (await self._session.execute(findings_count_query)).scalar_one()

        latest_scan_read: ScanResultRead | None = None
        if latest_scan_row is not None:
            latest_scan_read = ScanResultRead(
                id=latest_scan_row["id"],
                package_id=latest_scan_row["package_id"],
                package_name=package.name,
                latest_version=latest_scan_row["latest_version"],
                previous_version=latest_scan_row["previous_version"],
                status=latest_scan_row["status"],
                score=latest_scan_row["score"],
                risk_level=latest_scan_row["risk_level"],
                error_message=latest_scan_row["error_message"],
                started_at=latest_scan_row["started_at"],
                finished_at=latest_scan_row["finished_at"],
                created_at=latest_scan_row["created_at"],
            )

        return PackageDetail(
            id=package.id,
            name=package.name,
            latest_scanned_version=package.latest_scanned_version,
            last_scanned_at=package.last_scanned_at,
            latest_scan=latest_scan_read,
            versions_count=versions_count,
            findings_count=findings_count,
        )

    async def list_package_versions(
        self,
        package_name: str,
        pagination: Pagination,
    ) -> tuple[list[PackageVersionRead], int]:
        package = await self.get_by_name(package_name)
        if package is None:
            return [], 0

        count_query = select(func.count()).select_from(PackageVersionModel).where(
            PackageVersionModel.package_id == package.id
        )
        query = (
            select(PackageVersionModel)
            .where(PackageVersionModel.package_id == package.id)
            .order_by(PackageVersionModel.published_at.desc().nulls_last(), PackageVersionModel.id.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )

        rows = (await self._session.execute(query)).scalars().all()
        total = (await self._session.execute(count_query)).scalar_one()
        items = [
            PackageVersionRead(
                id=row.id,
                package_id=row.package_id,
                package_name=package.name,
                version=row.version,
                published_at=row.published_at,
                tarball_url=row.tarball_url,
                integrity=row.integrity,
                unpacked_size=row.unpacked_size,
                file_count=row.file_count,
                package_json=row.package_json,
                dependencies=row.dependencies,
                scripts=row.scripts,
                created_at=row.created_at,
            )
            for row in rows
        ]
        return items, total

    async def list_scan_results(
        self,
        filters: ScanResultFilters,
        pagination: Pagination,
    ) -> tuple[list[ScanResultRead], int]:
        count_query = select(func.count()).select_from(ScanResultModel).join(
            PackageModel, ScanResultModel.package_id == PackageModel.id
        )
        query = (
            select(ScanResultModel, PackageModel.name.label("package_name"))
            .join(PackageModel, ScanResultModel.package_id == PackageModel.id)
            .order_by(desc(ScanResultModel.started_at), desc(ScanResultModel.id))
            .limit(pagination.limit)
            .offset(pagination.offset)
        )

        count_query, query = self._apply_scan_filters(count_query, query, filters)

        rows = (await self._session.execute(query)).all()
        total = (await self._session.execute(count_query)).scalar_one()
        items = [
            ScanResultRead(
                id=row.ScanResultModel.id,
                package_id=row.ScanResultModel.package_id,
                package_name=row.package_name,
                latest_version=row.ScanResultModel.latest_version,
                previous_version=row.ScanResultModel.previous_version,
                status=row.ScanResultModel.status,
                score=row.ScanResultModel.score,
                risk_level=row.ScanResultModel.risk_level,
                error_message=row.ScanResultModel.error_message,
                started_at=row.ScanResultModel.started_at,
                finished_at=row.ScanResultModel.finished_at,
                created_at=row.ScanResultModel.created_at,
            )
            for row in rows
        ]
        return items, total

    async def list_findings(
        self,
        filters: FindingFilters,
        pagination: Pagination,
    ) -> tuple[list[FindingRead], int]:
        count_query = (
            select(func.count())
            .select_from(FindingModel)
            .join(ScanResultModel, FindingModel.scan_result_id == ScanResultModel.id)
            .join(PackageModel, ScanResultModel.package_id == PackageModel.id)
        )
        query = (
            select(FindingModel, ScanResultModel.package_id, PackageModel.name.label("package_name"))
            .join(ScanResultModel, FindingModel.scan_result_id == ScanResultModel.id)
            .join(PackageModel, ScanResultModel.package_id == PackageModel.id)
            .order_by(desc(FindingModel.created_at), desc(FindingModel.id))
            .limit(pagination.limit)
            .offset(pagination.offset)
        )

        if filters.severity:
            count_query = count_query.where(FindingModel.severity == filters.severity)
            query = query.where(FindingModel.severity == filters.severity)
        if filters.finding_type:
            count_query = count_query.where(FindingModel.finding_type == filters.finding_type)
            query = query.where(FindingModel.finding_type == filters.finding_type)
        if filters.package_name:
            like_pattern = f"%{filters.package_name}%"
            count_query = count_query.where(PackageModel.name.ilike(like_pattern))
            query = query.where(PackageModel.name.ilike(like_pattern))

        rows = (await self._session.execute(query)).all()
        total = (await self._session.execute(count_query)).scalar_one()
        items = [
            FindingRead(
                id=row.FindingModel.id,
                scan_result_id=row.FindingModel.scan_result_id,
                package_id=row.package_id,
                package_name=row.package_name,
                finding_type=row.FindingModel.finding_type,
                severity=row.FindingModel.severity,
                category=row.FindingModel.category,
                file_path=row.FindingModel.file_path,
                description=row.FindingModel.description,
                evidence=row.FindingModel.evidence,
                created_at=row.FindingModel.created_at,
            )
            for row in rows
        ]
        return items, total

    @staticmethod
    def _latest_scan_subquery(*, completed_only: bool = False):
        ranked_query = select(
            ScanResultModel.id,
            ScanResultModel.package_id,
            ScanResultModel.latest_version,
            ScanResultModel.previous_version,
            ScanResultModel.status,
            ScanResultModel.score,
            ScanResultModel.risk_level,
            ScanResultModel.error_message,
            ScanResultModel.started_at,
            ScanResultModel.finished_at,
            ScanResultModel.created_at,
            func.row_number()
            .over(
                partition_by=ScanResultModel.package_id,
                order_by=(ScanResultModel.started_at.desc(), ScanResultModel.id.desc()),
            )
            .label("row_number"),
        )
        if completed_only:
            ranked_query = ranked_query.where(ScanResultModel.status == ScanStatus.COMPLETED.value)
        ranked_subquery = ranked_query.subquery()
        return select(ranked_subquery).where(ranked_subquery.c.row_number == 1).subquery()

    @staticmethod
    def _apply_scan_filters(count_query, query, filters: ScanResultFilters):
        if filters.status:
            count_query = count_query.where(ScanResultModel.status == filters.status)
            query = query.where(ScanResultModel.status == filters.status)
        if filters.risk_level:
            count_query = count_query.where(ScanResultModel.risk_level == filters.risk_level)
            query = query.where(ScanResultModel.risk_level == filters.risk_level)
        if filters.package_name:
            like_pattern = f"%{filters.package_name}%"
            count_query = count_query.where(PackageModel.name.ilike(like_pattern))
            query = query.where(PackageModel.name.ilike(like_pattern))
        return count_query, query
