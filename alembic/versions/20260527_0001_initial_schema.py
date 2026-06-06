"""create initial persistence schema

Revision ID: 20260527_0001
Revises:
Create Date: 2026-05-27 00:01:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260527_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("latest_scanned_version", sa.String(length=128), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_packages_name"),
    )
    op.create_index("ix_packages_name", "packages", ["name"])

    op.create_table(
        "package_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tarball_url", sa.Text(), nullable=True),
        sa.Column("integrity", sa.Text(), nullable=True),
        sa.Column("unpacked_size", sa.Integer(), nullable=True),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("package_json", postgresql.JSONB(), nullable=False),
        sa.Column("dependencies", postgresql.JSONB(), nullable=False),
        sa.Column("scripts", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("package_id", "version", name="uq_package_versions_package_id_version"),
    )
    op.create_index("ix_package_versions_package_id", "package_versions", ["package_id"])

    op.create_table(
        "scan_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("latest_version", sa.String(length=128), nullable=False),
        sa.Column("previous_version", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_scan_results_status"),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high', 'unknown')", name="ck_scan_results_risk_level"),
        sa.ForeignKeyConstraint(["package_id"], ["packages.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_scan_results_package_id", "scan_results", ["package_id"])
    op.create_index(
        "uq_scan_results_package_latest_previous_not_null",
        "scan_results",
        ["package_id", "latest_version", "previous_version"],
        unique=True,
        postgresql_where=sa.text("previous_version IS NOT NULL"),
    )
    op.create_index(
        "uq_scan_results_package_latest_previous_null",
        "scan_results",
        ["package_id", "latest_version"],
        unique=True,
        postgresql_where=sa.text("previous_version IS NULL"),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scan_result_id", sa.Integer(), nullable=False),
        sa.Column("finding_type", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="ck_findings_severity"),
        sa.ForeignKeyConstraint(["scan_result_id"], ["scan_results.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_findings_scan_result_id", "findings", ["scan_result_id"])


def downgrade() -> None:
    op.drop_index("ix_findings_scan_result_id", table_name="findings")
    op.drop_table("findings")
    op.drop_index("uq_scan_results_package_latest_previous_null", table_name="scan_results")
    op.drop_index("uq_scan_results_package_latest_previous_not_null", table_name="scan_results")
    op.drop_index("ix_scan_results_package_id", table_name="scan_results")
    op.drop_table("scan_results")
    op.drop_index("ix_package_versions_package_id", table_name="package_versions")
    op.drop_table("package_versions")
    op.drop_index("ix_packages_name", table_name="packages")
    op.drop_table("packages")
