"""phase6 intelligence tables and indexes

Revision ID: 20260702_0002
Revises: 20260701_0001
Create Date: 2026-07-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260702_0002"
down_revision: Union[str, None] = "20260701_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "operator_profiles",
        sa.Column("query_preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "background_job_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("process_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entities_processed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("anomalies_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("anomalies_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("anomalies_resolved", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_job_runs_process_name", "background_job_runs", ["process_name"])

    op.create_table(
        "system_reports",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.Integer(), server_default="1", nullable=False),
        sa.Column("report_type", sa.String(length=50), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_system_reports_report_type", "system_reports", ["report_type"])

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_metrics_tenant_entity_metric_period
        ON fleet_metrics (tenant_id, entity_type, entity_id, metric_name, period_type, period_start);
        """
    )

    for table in ("background_job_runs", "system_reports"):
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_fleet_metrics_tenant_entity_metric_period")
    op.drop_table("system_reports")
    op.drop_table("background_job_runs")
    op.drop_column("operator_profiles", "query_preferences")
