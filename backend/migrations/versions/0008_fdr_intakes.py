from alembic import op
import sqlalchemy as sa

revision = "0008_fdr_intakes"
down_revision = "0007_extraction_results"


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("fdr_intakes"):
        op.create_table(
            "fdr_intakes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
            sa.Column("source_fdr_id", sa.Integer(), sa.ForeignKey("fdrs.id"), nullable=False),
            sa.Column("candidate_fields", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending_completion"),
            sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("fdr_intakes")}
    if "ix_fdr_intakes_source_document_id" not in indexes:
        op.create_index("ix_fdr_intakes_source_document_id", "fdr_intakes", ["source_document_id"])
    if "ix_fdr_intakes_source_fdr_id" not in indexes:
        op.create_index("ix_fdr_intakes_source_fdr_id", "fdr_intakes", ["source_fdr_id"])


def downgrade():
    op.drop_index("ix_fdr_intakes_source_fdr_id", table_name="fdr_intakes")
    op.drop_index("ix_fdr_intakes_source_document_id", table_name="fdr_intakes")
    op.drop_table("fdr_intakes")
