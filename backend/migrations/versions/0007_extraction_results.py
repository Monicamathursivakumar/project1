from alembic import op
import sqlalchemy as sa

revision = "0007_extraction_results"
down_revision = "0006_institution_memberships"


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("extraction_results"):
        op.create_table(
            "extraction_results",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("provider", sa.String(length=100), nullable=False, server_default="local-pymupdf"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="completed"),
            sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("extracted_text", sa.Text(), nullable=False, server_default=""),
            sa.Column("authenticity_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_extraction_results_document_id" not in {index["name"] for index in sa.inspect(bind).get_indexes("extraction_results")}:
        op.create_index("ix_extraction_results_document_id", "extraction_results", ["document_id"])


def downgrade():
    op.drop_index("ix_extraction_results_document_id", table_name="extraction_results")
    op.drop_table("extraction_results")
