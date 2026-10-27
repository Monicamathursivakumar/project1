from alembic import op
import sqlalchemy as sa

revision = "0006_institution_memberships"
down_revision = "0005_institution_dataset"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("user_institution_memberships"):
        op.create_table(
            "user_institution_memberships",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("user_institution_memberships")}
    for name, column in (
        ("ix_user_institution_memberships_user_id", "user_id"),
        ("ix_user_institution_memberships_institution_id", "institution_id"),
    ):
        if name not in indexes:
            op.create_index(name, "user_institution_memberships", [column])


def downgrade():
    op.drop_index("ix_user_institution_memberships_institution_id", table_name="user_institution_memberships")
    op.drop_index("ix_user_institution_memberships_user_id", table_name="user_institution_memberships")
    op.drop_table("user_institution_memberships")
