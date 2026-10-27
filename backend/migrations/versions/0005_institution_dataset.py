from alembic import op
import sqlalchemy as sa

revision = "0005_institution_dataset"
down_revision = "0004_fdr_registration_fields"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    institution_columns = {column["name"] for column in inspector.get_columns("institutions")}
    columns = (
        ("aicte_id", sa.String(length=100), True, None),
        ("other_id", sa.String(length=100), True, None),
        ("district", sa.String(length=150), False, ""),
        ("state", sa.String(length=150), False, ""),
        ("institution_type", sa.String(length=100), False, ""),
        ("women", sa.String(length=10), False, ""),
        ("minority", sa.String(length=10), False, ""),
        ("university", sa.String(length=500), False, ""),
    )
    for name, type_, nullable, default in columns:
        if name not in institution_columns:
            op.add_column("institutions", sa.Column(name, type_, nullable=nullable, server_default=default))
    existing_indexes = {index["name"] for index in inspector.get_indexes("institutions")}
    for name, column, unique in (
        ("ix_institutions_aicte_id", "aicte_id", True),
        ("ix_institutions_other_id", "other_id", False),
        ("ix_institutions_district", "district", False),
        ("ix_institutions_state", "state", False),
        ("ix_institutions_institution_type", "institution_type", False),
    ):
        if name not in existing_indexes:
            op.create_index(name, "institutions", [column], unique=unique)
    if not inspector.has_table("institution_programmes"):
        op.create_table(
            "institution_programmes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
            sa.Column("programme", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("level", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("course", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("course_type", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("shift", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("availability", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("intake", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("enrollment", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("placement", sa.String(length=50), nullable=False, server_default=""),
        )
    if "ix_institution_programmes_institution_id" not in {index["name"] for index in sa.inspect(bind).get_indexes("institution_programmes")}:
        op.create_index("ix_institution_programmes_institution_id", "institution_programmes", ["institution_id"])


def downgrade():
    op.drop_index("ix_institution_programmes_institution_id", table_name="institution_programmes")
    op.drop_table("institution_programmes")
    for name in (
        "ix_institutions_institution_type",
        "ix_institutions_state",
        "ix_institutions_district",
        "ix_institutions_other_id",
        "ix_institutions_aicte_id",
    ):
        op.drop_index(name, table_name="institutions")
    for column in ("university", "minority", "women", "institution_type", "state", "district", "other_id", "aicte_id"):
        op.drop_column("institutions", column)
