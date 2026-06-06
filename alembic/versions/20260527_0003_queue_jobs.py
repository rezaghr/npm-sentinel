"""add durable queue job lifecycle table

Revision ID: 20260527_0003
Revises: 20260527_0002
Create Date: 2026-05-27 14:30:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260527_0003"
down_revision: str | None = "20260527_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "queue_jobs",
        sa.Column("task_id", sa.String(length=64), primary_key=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "job_type IN ('scan_package', 'top_packages_batch')",
            name="ck_queue_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed')",
            name="ck_queue_jobs_status",
        ),
    )
    op.create_index("ix_queue_jobs_package_name", "queue_jobs", ["package_name"])
    op.create_index("ix_queue_jobs_status_created_at", "queue_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_queue_jobs_status_created_at", table_name="queue_jobs")
    op.drop_index("ix_queue_jobs_package_name", table_name="queue_jobs")
    op.drop_table("queue_jobs")
