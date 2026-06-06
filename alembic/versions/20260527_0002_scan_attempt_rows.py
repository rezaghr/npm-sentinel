"""make scan results durable attempt rows

Revision ID: 20260527_0002
Revises: 20260527_0001
Create Date: 2026-05-27 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260527_0002"
down_revision: str | None = "20260527_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_scan_results_package_latest_previous_null", table_name="scan_results")
    op.drop_index("uq_scan_results_package_latest_previous_not_null", table_name="scan_results")
    op.alter_column("scan_results", "latest_version", existing_type=sa.String(length=128), nullable=True)
    op.create_index(
        "ix_scan_results_package_latest_previous",
        "scan_results",
        ["package_id", "latest_version", "previous_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scan_results_package_latest_previous", table_name="scan_results")
    op.alter_column("scan_results", "latest_version", existing_type=sa.String(length=128), nullable=False)
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
