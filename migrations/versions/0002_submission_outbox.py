"""Persist transport selection and transactional SQS publication intent."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspections",
        sa.Column(
            "queue_backend",
            sa.String(16),
            nullable=False,
            server_default="database",
        ),
    )
    op.create_table(
        "submission_outbox",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "inspection_id",
            sa.String(36),
            sa.ForeignKey("inspections.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("available_at", sa.Float(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.Float(), nullable=True),
        sa.Column("lease_token", sa.String(36), nullable=True),
        sa.Column("lease_until", sa.Float(), nullable=True),
    )
    op.create_index(
        "ix_outbox_pending", "submission_outbox", ["published_at", "available_at", "lease_until"]
    )


def downgrade() -> None:
    # Removing outstanding delivery intent would strand jobs, including on rollback.
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT count(*) FROM inspections WHERE queue_backend = 'sqs'")
    ).scalar():
        raise RuntimeError("Cannot downgrade while SQS inspection records exist")
    op.drop_table("submission_outbox")
    op.drop_column("inspections", "queue_backend")
