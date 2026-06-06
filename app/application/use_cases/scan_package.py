from __future__ import annotations

import logging
from time import perf_counter
from pathlib import Path
from tempfile import TemporaryDirectory

from app.application.ports.package_registry import (
    PackageRegistry,
    PackageVersionMetadata as RegistryPackageVersionMetadata,
)
from app.application.ports.package_repository import FindingCreate, PackageVersionMetadata
from app.application.ports.scanner import ArchiveExtractor, PackageAnalyzer, TarballDownloader
from app.application.ports.unit_of_work import RepositoryUnitOfWorkFactory
from app.domain.findings import Finding
from app.domain.scoring import calculate_risk_level, calculate_score

logger = logging.getLogger(__name__)


class ScanPackageUseCase:
    def __init__(
        self,
        *,
        repository_unit_of_work_factory: RepositoryUnitOfWorkFactory,
        package_registry: PackageRegistry,
        tarball_downloader: TarballDownloader,
        extractor: ArchiveExtractor,
        analyzer: PackageAnalyzer,
    ) -> None:
        self._repository_unit_of_work_factory = repository_unit_of_work_factory
        self._package_registry = package_registry
        self._tarball_downloader = tarball_downloader
        self._extractor = extractor
        self._analyzer = analyzer

    async def execute(self, package_name: str, reason: str = "manual") -> None:
        scan_result_id: int | None = None
        package_id: int | None = None
        latest_version: str | None = None
        previous_version: str | None = None
        started_at = perf_counter()

        logger.info(
            "scan_started",
            extra={"package_name": package_name, "job_reason": reason},
        )

        with TemporaryDirectory(prefix="scan-package-") as temp_root_str:
            temp_root = Path(temp_root_str)
            latest_download_dir = temp_root / "latest" / "download"
            latest_extract_dir = temp_root / "latest" / "extract"
            previous_download_dir = temp_root / "previous" / "download"
            previous_extract_dir = temp_root / "previous" / "extract"

            try:
                async with self._repository_unit_of_work_factory() as repository:
                    package_row = await repository.upsert_package(package_name)
                    package_id = package_row.id
                    queued_scan = await repository.claim_next_queued_scan(package_row.id)
                    if queued_scan is not None:
                        scan_result_id = queued_scan.id
                    else:
                        scan_result = await repository.create_scan_result(
                            package_row.id,
                            latest_version=None,
                            previous_version=None,
                            status="running",
                        )
                        scan_result_id = scan_result.id

                logger.info(
                    "metadata_fetch_started",
                    extra={"package_name": package_name},
                )
                metadata = await self._package_registry.fetch_metadata(package_name)
                latest_version = metadata.latest_version.version
                previous_version = (
                    metadata.previous_version.version if metadata.previous_version else None
                )
                logger.info(
                    "metadata_fetch_completed",
                    extra={
                        "package_name": metadata.package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                    },
                )

                async with self._repository_unit_of_work_factory() as repository:
                    await repository.upsert_package_version(
                        package_id,
                        metadata.latest_version.version,
                        self._to_repository_metadata(metadata.latest_version),
                    )
                    if metadata.previous_version is not None:
                        await repository.upsert_package_version(
                            package_id,
                            metadata.previous_version.version,
                            self._to_repository_metadata(metadata.previous_version),
                        )
                    if scan_result_id is None:
                        raise RuntimeError("scan_result_id should exist before setting versions")
                    await repository.set_scan_versions(
                        scan_result_id,
                        metadata.latest_version.version,
                        previous_version,
                    )

                logger.info(
                    "tarball_download_started",
                    extra={
                        "package_name": package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                        "target_version": latest_version,
                    },
                )
                latest_tarball_path = await self._tarball_downloader.download(
                    metadata.latest_version.tarball_url,
                    latest_download_dir,
                    integrity=metadata.latest_version.integrity,
                )
                logger.info(
                    "tarball_download_completed",
                    extra={
                        "package_name": package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                        "target_version": latest_version,
                    },
                )
                latest_extracted_root = self._extractor.extract(latest_tarball_path, latest_extract_dir)
                logger.info(
                    "tarball_extracted",
                    extra={
                        "package_name": package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                        "target_version": latest_version,
                    },
                )

                previous_extracted_root: Path | None = None
                if metadata.previous_version is not None:
                    logger.info(
                        "tarball_download_started",
                        extra={
                            "package_name": package_name,
                            "latest_version": latest_version,
                            "previous_version": previous_version,
                            "target_version": previous_version,
                        },
                    )
                    previous_tarball_path = await self._tarball_downloader.download(
                        metadata.previous_version.tarball_url,
                        previous_download_dir,
                        integrity=metadata.previous_version.integrity,
                    )
                    logger.info(
                        "tarball_download_completed",
                        extra={
                            "package_name": package_name,
                            "latest_version": latest_version,
                            "previous_version": previous_version,
                            "target_version": previous_version,
                        },
                    )
                    previous_extracted_root = self._extractor.extract(previous_tarball_path, previous_extract_dir)
                    logger.info(
                        "tarball_extracted",
                        extra={
                            "package_name": package_name,
                            "latest_version": latest_version,
                            "previous_version": previous_version,
                            "target_version": previous_version,
                        },
                    )

                findings = self._analyzer.analyze(
                    latest_root=latest_extracted_root,
                    latest_metadata_scripts=metadata.latest_version.scripts,
                    latest_size=metadata.latest_version.unpacked_size,
                    previous_root=previous_extracted_root,
                    previous_metadata_scripts=metadata.previous_version.scripts if metadata.previous_version else None,
                    previous_size=metadata.previous_version.unpacked_size if metadata.previous_version else None,
                )

                score = calculate_score(findings)
                risk_level = calculate_risk_level(score)
                persisted_findings = [self._to_finding_create(finding) for finding in findings]
                for finding in findings:
                    logger.info(
                        "finding_detected",
                        extra={
                            "package_name": package_name,
                            "latest_version": latest_version,
                            "previous_version": previous_version,
                            "scan_result_id": scan_result_id,
                            "finding_type": finding.finding_type.value,
                            "severity": finding.severity.value,
                            "category": finding.category,
                            "file_path": finding.file_path,
                        },
                    )

                async with self._repository_unit_of_work_factory() as repository:
                    if scan_result_id is None:
                        raise RuntimeError("scan_result_id should exist before marking completed")
                    if package_id is None:
                        raise RuntimeError("package_id should exist before marking completed")
                    await repository.replace_findings(scan_result_id, persisted_findings)
                    await repository.mark_scan_completed(scan_result_id, score, risk_level)
                    await repository.mark_package_scanned(package_id, metadata.latest_version.version)
                logger.info(
                    "scan_result_saved",
                    extra={
                        "package_name": package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                        "scan_result_id": scan_result_id,
                        "score": score,
                        "risk_level": risk_level,
                    },
                )

                logger.info(
                    "scan_completed",
                    extra={
                        "package_name": metadata.package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                        "job_reason": reason,
                        "scan_result_id": scan_result_id,
                        "score": score,
                        "risk_level": risk_level,
                        "duration_ms": int((perf_counter() - started_at) * 1000),
                        "finding_count": len(findings),
                    },
                )
            except Exception as exc:
                error_message = self._safe_error_message(exc)
                if scan_result_id is not None:
                    await self._mark_scan_failed(scan_result_id, error_message)
                logger.exception(
                    "scan_failed",
                    extra={
                        "package_name": package_name,
                        "latest_version": latest_version,
                        "previous_version": previous_version,
                        "job_reason": reason,
                        "scan_result_id": scan_result_id,
                        "duration_ms": int((perf_counter() - started_at) * 1000),
                        "error_type": exc.__class__.__name__,
                        "error_message": error_message,
                    },
                )
                raise

    async def _mark_scan_failed(self, scan_result_id: int, error_message: str) -> None:
        try:
            async with self._repository_unit_of_work_factory() as repository:
                await repository.mark_scan_failed(scan_result_id, error_message)
        except Exception:
            logger.exception(
                "scan_failure_persist_failed",
                extra={"scan_result_id": scan_result_id},
            )

    @staticmethod
    def _to_repository_metadata(metadata: RegistryPackageVersionMetadata) -> PackageVersionMetadata:
        return PackageVersionMetadata(
            published_at=metadata.published_at,
            tarball_url=metadata.tarball_url,
            integrity=metadata.integrity,
            unpacked_size=metadata.unpacked_size,
            file_count=metadata.file_count,
            package_json=dict(metadata.package_json),
            dependencies=dict(metadata.dependencies),
            scripts=dict(metadata.scripts),
        )

    @staticmethod
    def _to_finding_create(finding: Finding) -> FindingCreate:
        return FindingCreate(
            finding_type=finding.finding_type.value,
            severity=finding.severity.value,
            category=finding.category,
            description=finding.description,
            file_path=finding.file_path,
            evidence=finding.evidence,
        )

    @staticmethod
    def _safe_error_message(exc: Exception, max_length: int = 500) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        if len(message) > max_length:
            return f"{message[:max_length]}..."
        return message
