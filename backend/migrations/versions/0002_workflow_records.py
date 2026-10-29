from alembic import op
import sqlalchemy as sa

revision = "0002_workflow_records"
down_revision = "0001_initial"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("policy_rules"):
        op.create_table(
            "policy_rules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("rule_id", sa.String(100), nullable=False, unique=True),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("required_documents", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("amount_floor", sa.Float(), nullable=False, server_default="0"),
            sa.Column("effective_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expiry_date", sa.DateTime(timezone=True)),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("source_reference", sa.String(500), nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        )
    if not inspector.has_table("deposit_assessments"):
        op.create_table(
            "deposit_assessments",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
            sa.Column("policy_rule_id", sa.Integer(), sa.ForeignKey("policy_rules.id")),
            sa.Column("amount", sa.Float()),
            sa.Column("status", sa.String(30), nullable=False, server_default="policy_required"),
            sa.Column("notes", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("import_jobs"):
        op.create_table(
            "import_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("valid_rows", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not inspector.has_table("import_row_errors"):
        op.create_table(
            "import_row_errors",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("job_id", sa.Integer(), sa.ForeignKey("import_jobs.id"), nullable=False),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("raw_data", sa.Text(), nullable=False),
        )


def downgrade():
    op.drop_table("import_row_errors")
    op.drop_table("import_jobs")
    op.drop_table("deposit_assessments")
    op.drop_table("policy_rules")
