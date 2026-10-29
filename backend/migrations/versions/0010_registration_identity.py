from alembic import op
import sqlalchemy as sa

revision = "0010_registration_identity"
down_revision = "0009_discrepancy_review"


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name == "postgresql":
        enum_names = {item["name"] for item in inspector.get_enums()}
        if "role" in enum_names:
            op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'institution_user'")
            op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'verification_officer'")

    if inspector.has_table("users"):
        user_columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
        if "email" not in user_columns:
            op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    if "ix_users_email" not in {index["name"] for index in sa.inspect(bind).get_indexes("users")}:
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not sa.inspect(bind).has_table("registration_requests"):
        op.create_table(
            "registration_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("public_id", sa.String(length=36), nullable=False, unique=True),
            sa.Column("username", sa.String(length=100), nullable=False, unique=True),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("email", sa.String(length=320), nullable=False, unique=True),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column("account_type", sa.String(length=40), nullable=False),
            sa.Column("organization_name", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("institution_id", sa.Integer(), sa.ForeignKey("institutions.id")),
            sa.Column("employee_id", sa.String(length=100), unique=True),
            sa.Column("department", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("designation", sa.String(length=150), nullable=False, server_default=""),
            sa.Column("email_verified_at", sa.DateTime(timezone=True)),
            sa.Column("identity_status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("employee_status", sa.String(length=30), nullable=False, server_default="not_required"),
            sa.Column("institution_status", sa.String(length=30), nullable=False, server_default="not_required"),
            sa.Column("role_status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending_email_verification"),
            sa.Column("github_provider_id", sa.String(length=100)),
            sa.Column("github_login", sa.String(length=100)),
            sa.Column("github_verified_at", sa.DateTime(timezone=True)),
            sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("decision_actor_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("decision_at", sa.DateTime(timezone=True)),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("registration_requests")}
    for name, column in (
        ("ix_registration_requests_public_id", "public_id"),
        ("ix_registration_requests_username", "username"),
        ("ix_registration_requests_email", "email"),
        ("ix_registration_requests_institution_id", "institution_id"),
        ("ix_registration_requests_status", "status"),
    ):
        if name not in indexes:
            op.create_index(name, "registration_requests", [column], unique=column in {"public_id", "username", "email"})

    if not sa.inspect(bind).has_table("employee_verifications"):
        op.create_table(
            "employee_verifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=False, unique=True),
            sa.Column("employee_id", sa.String(length=100), nullable=False, unique=True),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("official_email", sa.String(length=320), nullable=False),
            sa.Column("organization_name", sa.String(length=255), nullable=False),
            sa.Column("department", sa.String(length=150), nullable=False),
            sa.Column("designation", sa.String(length=150), nullable=False),
            sa.Column("requested_role", sa.String(length=40), nullable=False),
            sa.Column("method", sa.String(length=40), nullable=False, server_default="manual_review"),
            sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
            sa.Column("evidence_reference", sa.String(length=500), nullable=False, server_default=""),
            sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("reviewed_at", sa.DateTime(timezone=True)),
            sa.Column("decision_reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_employee_verifications_registration_id" not in {index["name"] for index in sa.inspect(bind).get_indexes("employee_verifications")}:
        op.create_index("ix_employee_verifications_registration_id", "employee_verifications", ["registration_id"], unique=True)

    if not sa.inspect(bind).has_table("auth_token_records"):
        op.create_table(
            "auth_token_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id")),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("purpose", sa.String(length=30), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("auth_token_records")}
    for name, column in (("ix_auth_token_records_registration_id", "registration_id"), ("ix_auth_token_records_user_id", "user_id"), ("ix_auth_token_records_token_hash", "token_hash")):
        if name not in indexes:
            op.create_index(name, "auth_token_records", [column], unique=column == "token_hash")

    if not sa.inspect(bind).has_table("github_oauth_states"):
        op.create_table(
            "github_oauth_states",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=False),
            sa.Column("state_hash", sa.String(length=64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("github_oauth_states")}
    for name, column in (("ix_github_oauth_states_registration_id", "registration_id"), ("ix_github_oauth_states_state_hash", "state_hash")):
        if name not in indexes:
            op.create_index(name, "github_oauth_states", [column], unique=column == "state_hash")

    if not sa.inspect(bind).has_table("registration_audit_events"):
        op.create_table(
            "registration_audit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("registration_id", sa.Integer(), sa.ForeignKey("registration_requests.id"), nullable=False),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id")),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("previous_status", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("new_status", sa.String(length=50), nullable=False, server_default=""),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "ix_registration_audit_events_registration_id" not in {index["name"] for index in sa.inspect(bind).get_indexes("registration_audit_events")}:
        op.create_index("ix_registration_audit_events_registration_id", "registration_audit_events", ["registration_id"])


def downgrade():
    op.drop_index("ix_registration_audit_events_registration_id", table_name="registration_audit_events")
    op.drop_table("registration_audit_events")
    op.drop_index("ix_github_oauth_states_state_hash", table_name="github_oauth_states")
    op.drop_index("ix_github_oauth_states_registration_id", table_name="github_oauth_states")
    op.drop_table("github_oauth_states")
    op.drop_index("ix_auth_token_records_token_hash", table_name="auth_token_records")
    op.drop_index("ix_auth_token_records_user_id", table_name="auth_token_records")
    op.drop_index("ix_auth_token_records_registration_id", table_name="auth_token_records")
    op.drop_table("auth_token_records")
    op.drop_index("ix_employee_verifications_registration_id", table_name="employee_verifications")
    op.drop_table("employee_verifications")
    for name in (
        "ix_registration_requests_status",
        "ix_registration_requests_institution_id",
        "ix_registration_requests_email",
        "ix_registration_requests_username",
        "ix_registration_requests_public_id",
    ):
        op.drop_index(name, table_name="registration_requests")
    op.drop_table("registration_requests")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email")
