from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ScanStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QueueJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PackageModel(Base):
    __tablename__ = "packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    latest_scanned_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions: Mapped[list["PackageVersionModel"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
    )
    scan_results: Mapped[list["ScanResultModel"]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
    )


class PackageVersionModel(Base):
    __tablename__ = "package_versions"
    __table_args__ = (UniqueConstraint("package_id", "version", name="uq_package_versions_package_id_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(128), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tarball_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    integrity: Mapped[str | None] = mapped_column(Text, nullable=True)
    unpacked_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    package_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    dependencies: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    scripts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package: Mapped[PackageModel] = relationship(back_populates="versions")


class ScanResultModel(Base):
    __tablename__ = "scan_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_scan_results_status",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'unknown')",
            name="ck_scan_results_risk_level",
        ),
        Index("ix_scan_results_package_latest_previous", "package_id", "latest_version", "previous_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id", ondelete="CASCADE"), nullable=False, index=True)
    latest_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    previous_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=ScanStatus.RUNNING.value)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default=RiskLevel.UNKNOWN.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    package: Mapped[PackageModel] = relationship(back_populates="scan_results")
    findings: Mapped[list["FindingModel"]] = relationship(
        back_populates="scan_result",
        cascade="all, delete-orphan",
    )


class FindingModel(Base):
    __tablename__ = "findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_findings_severity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_result_id: Mapped[int] = mapped_column(
        ForeignKey("scan_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    scan_result: Mapped[ScanResultModel] = relationship(back_populates="findings")


class QueueJobModel(Base):
    __tablename__ = "queue_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('scan_package', 'top_packages_batch')",
            name="ck_queue_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_queue_jobs_status",
        ),
        Index("ix_queue_jobs_status_created_at", "status", "created_at"),
    )

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(32), nullable=False)
    package_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=QueueJobStatus.QUEUED.value)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
