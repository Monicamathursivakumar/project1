from alembic import op
import sqlalchemy as sa

revision = "0009_discrepancy_review"
down_revision = "0008_fdr_intakes"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("discrepancy_analysis_details"):
        op.create_table(
            "discrepancy_analysis_details",
            sa.Column("discrepancy_id", sa.Integer(), sa.ForeignKey("discrepancies.id"), primary_key=True),
            sa.Column("title", sa.String(255), nullable=False, server_default=""),
            sa.Column("affected_field", sa.String(100), nullable=False, server_default=""),
            sa.Column("expected_source", sa.String(500), nullable=False, server_default=""),
            sa.Column("observed_source", sa.String(500), nullable=False, server_default=""),
            sa.Column("recommended_action", sa.Text(), nullable=False, server_default=""),
            sa.Column("evidence_reference", sa.String(1000), nullable=False, server_default=""),
            sa.Column("analysis_method", sa.String(50), nullable=False, server_default="rule_based"),
            sa.Column("review_status", sa.String(40), nullable=False, server_default="pending"),
        )
    if not inspector.has_table("discrepancy_review_events"):
        op.create_table(
            "discrepancy_review_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("discrepancy_id", sa.Integer(), sa.ForeignKey("discrepancies.id"), nullable=False),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("action", sa.String(40), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_discrepancy_review_events_discrepancy_id" not in {
        index["name"] for index in sa.inspect(bind).get_indexes("discrepancy_review_events")
    }:
        op.create_index(
            "ix_discrepancy_review_events_discrepancy_id",
            "discrepancy_review_events",
            ["discrepancy_id"],
        )


def downgrade():
    op.drop_index("ix_discrepancy_review_events_discrepancy_id", table_name="discrepancy_review_events")
    op.drop_table("discrepancy_review_events")
    op.drop_table("discrepancy_analysis_details")
