from alembic import op
import sqlalchemy as sa


revision = "0011_registration_identity_documents"
down_revision = "0010_registration_identity"


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("registration_requests"):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("registration_requests")}
    for name, column_type in (
        ("identity_document_stored_name", sa.String(length=255)),
        ("identity_document_sha256", sa.String(length=64)),
        ("identity_document_content_type", sa.String(length=100)),
        ("identity_document_size", sa.Integer()),
        ("identity_document_uploaded_at", sa.DateTime(timezone=True)),
    ):
        if name not in columns:
            op.add_column("registration_requests", sa.Column(name, column_type, nullable=True))


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("registration_requests"):
        return
    columns = {column["name"] for column in sa.inspect(bind).get_columns("registration_requests")}
    for name in (
        "identity_document_uploaded_at",
        "identity_document_size",
        "identity_document_content_type",
        "identity_document_sha256",
        "identity_document_stored_name",
    ):
        if name in columns:
            op.drop_column("registration_requests", name)
