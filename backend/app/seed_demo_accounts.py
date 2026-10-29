"""Seed opt-in, local-only department demo accounts."""

from __future__ import annotations

import os

from sqlalchemy import select

from .main import (
    AuditEvent,
    Institution,
    Role,
    SessionLocal,
    User,
    UserInstitutionMembership,
    pwd_context,
)


DEMO_ROLES = {
    "demo_institution_user": Role.institution_user,
    "demo_reviewing_officer": Role.reviewer,
    "demo_verification_officer": Role.verification_officer,
    "demo_custody_officer": Role.custody,
    "demo_policy_administrator": Role.policy_admin,
    "demo_auditor": Role.auditor,
    "demo_administrator": Role.admin,
    "demo_viewer": Role.viewer,
}


def main() -> None:
    if os.getenv("ENABLE_DEMO_ACCOUNTS", "").casefold() != "true":
        raise SystemExit("Set ENABLE_DEMO_ACCOUNTS=true to explicitly enable local demo accounts.")
    if os.getenv("APP_ENVIRONMENT", "development").casefold() == "production" or os.getenv("RENDER"):
        raise SystemExit("Demo accounts are disabled in production and on Render.")
    password = os.getenv("DEMO_ACCOUNT_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("Set DEMO_ACCOUNT_PASSWORD to a unique password of at least 12 characters.")

    with SessionLocal() as db:
        institution = db.scalar(select(Institution).order_by(Institution.id))
        if not institution:
            raise SystemExit("Load the institution catalogue before seeding department demo accounts.")
        admin = db.scalar(select(User).where(User.role == Role.admin).order_by(User.id))
        created: list[str] = []
        for username, role in DEMO_ROLES.items():
            account = db.scalar(select(User).where(User.username == username))
            if not account:
                account = User(
                    username=username,
                    email=f"{username}@example.test",
                    password_hash=pwd_context.hash(password),
                    role=role,
                    active=True,
                )
                db.add(account)
                db.flush()
                created.append(username)
            membership = db.scalar(select(UserInstitutionMembership).where(
                UserInstitutionMembership.user_id == account.id,
                UserInstitutionMembership.institution_id == institution.id,
            ))
            if not membership:
                db.add(UserInstitutionMembership(
                    user_id=account.id,
                    institution_id=institution.id,
                ))
            if admin:
                db.add(AuditEvent(
                    actor_id=admin.id,
                    action="demo_account_seeded",
                    entity="user",
                    entity_id=str(account.id),
                    details=f"Local demo account for role {role.value}.",
                ))
        db.commit()
    print(f"Created {len(created)} department demo accounts.")
    print("Accounts: " + ", ".join(DEMO_ROLES))
    print("Use the configured DEMO_ACCOUNT_PASSWORD. The bootstrapped administrator was not changed.")


if __name__ == "__main__":
    main()
