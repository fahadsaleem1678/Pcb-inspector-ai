"""Keep backend-owned inspection tables private on Supabase.

The portfolio uses PostgreSQL through the Python API, not Supabase's Data API.
No browser role receives table access or an RLS policy.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("inspections", "inspection_events", "submission_outbox"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM PUBLIC")
    # Supabase defines these roles; ordinary local PostgreSQL may not.
    op.execute(
        """
        DO $$
        DECLARE app_role text;
        BEGIN
            FOREACH app_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = app_role) THEN
                    EXECUTE format(
                        'REVOKE ALL PRIVILEGES ON TABLE inspections, '
                        'inspection_events, submission_outbox FROM %I', app_role
                    );
                END IF;
            END LOOP;
        END $$
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("inspections", "inspection_events", "submission_outbox"):
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    # Revoked grants are intentionally not recreated on downgrade.
