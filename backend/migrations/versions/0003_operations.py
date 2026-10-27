from alembic import op
import sqlalchemy as sa

revision = "0003_operations"
down_revision = "0002_workflow_records"


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        for value in ("custody", "auditor", "policy_admin"):
            op.execute(f"ALTER TYPE role ADD VALUE IF NOT EXISTS '{value}'")
    op.create_table(
        "lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fdr_id", sa.Integer(), sa.ForeignKey("fdrs.id"), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=False),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "custody_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fdr_id", sa.Integer(), sa.ForeignKey("fdrs.id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("location", sa.String(255), nullable=False),
        sa.Column("custodian", sa.String(255), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=False, server_default=""),
        sa.Column("remarks", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fdr_id", sa.Integer(), sa.ForeignKey("fdrs.id"), nullable=False),
        sa.Column("channel", sa.String(30), nullable=False),
        sa.Column("reminder_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="planned"),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("notification_events")
    op.drop_table("custody_events")
    op.drop_table("lifecycle_events")
