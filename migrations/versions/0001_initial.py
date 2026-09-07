"""Initial durable inspections and event log."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(128), nullable=False),
        sa.Column("image_key", sa.String(512), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("completed_at", sa.Float(), nullable=True),
        sa.Column("available_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("overall_result", sa.String(64), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_inspections_queue", "inspections", ["status", "available_at", "lease_until"]
    )
    op.create_index("ix_inspections_owner_created", "inspections", ["owner_id", "created_at", "id"])
    op.create_table(
        "inspection_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("inspection_id", sa.String(36), sa.ForeignKey("inspections.id"), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("event_data", sa.JSON(), nullable=False),
    )
    op.create_index("ix_events_inspection", "inspection_events", ["inspection_id", "created_at"])


def downgrade() -> None:
    op.drop_table("inspection_events")
    op.drop_table("inspections")
