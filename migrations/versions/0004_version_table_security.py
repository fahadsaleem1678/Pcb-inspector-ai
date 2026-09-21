"""Restrict the Alembic version table from Supabase browser roles."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE alembic_version ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM PUBLIC")
    op.execute(
        """
        DO $$
        DECLARE app_role text;
        BEGIN
            FOREACH app_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
                    EXECUTE format(
                        'REVOKE ALL PRIVILEGES ON TABLE alembic_version FROM %I', app_role
                    );
                END IF;
            END LOOP;
        END $$
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE alembic_version DISABLE ROW LEVEL SECURITY")
    # Revoked grants are intentionally not recreated on downgrade.
