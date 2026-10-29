from alembic import op
import sqlalchemy as sa

revision = "0004_fdr_registration_fields"
down_revision = "0003_operations"


def upgrade():
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("fdrs")}
    columns = [
        ("approval_case_reference", sa.String(100)),
        ("bank_name", sa.String(255)),
        ("branch_name", sa.String(255)),
        ("ifsc_code", sa.String(20)),
        ("amount_in_words", sa.String(500)),
        ("issue_date", sa.DateTime(timezone=True)),
        ("beneficiary", sa.String(500)),
        ("joint_holder", sa.String(255)),
        ("lien_endorsed", sa.Boolean(), False),
        ("lien_clause", sa.Text()),
    ]
    for column in columns:
        name, type_, *default = column
        if name not in existing_columns:
            op.add_column("fdrs", sa.Column(name, type_, nullable=True, server_default=str(default[0]).lower() if default else None))


def downgrade():
    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("fdrs")}
    for name in ("lien_clause", "lien_endorsed", "joint_holder", "beneficiary", "issue_date", "amount_in_words", "ifsc_code", "branch_name", "bank_name", "approval_case_reference"):
        if name in existing_columns:
            op.drop_column("fdrs", name)
