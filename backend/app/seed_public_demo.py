"""Seed role-specific synthetic data for the read-only public demo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .main import (
    DepositAssessment,
    FieldProvenance,
    Fdr,
    FdrStatus,
    InstrumentVersion,
    Institution,
    LifecycleEvent,
    PolicyRule,
    ProvenanceLevel,
    Role,
    SessionLocal,
    User,
    UserInstitutionMembership,
    VerificationCase,
    VerificationStatus,
    pwd_context,
)


PUBLIC_DEMO_PASSWORD = "VaultTrace-Demo-2026!"

DEMO_ROLES = {
    "demo_administrator": Role.admin,
    "demo_auditor": Role.auditor,
    "demo_institution_user": Role.institution_user,
    "demo_reviewing_officer": Role.reviewer,
    "demo_verification_officer": Role.verification_officer,
    "demo_custody_officer": Role.custody,
    "demo_policy_administrator": Role.policy_admin,
    "demo_viewer": Role.viewer,
}

INSTITUTIONS = (
    "Northstar Institute of Engineering",
    "Eastfield Polytechnic",
    "Riverbend Technical College",
    "Summit School of Technology",
    "Lakeside Institute of Design",
    "Greenfield Management College",
)

ROLE_INSTITUTIONS = {
    "demo_institution_user": 1,
    "demo_reviewing_officer": 2,
    "demo_verification_officer": 3,
    "demo_custody_officer": 4,
    "demo_viewer": 5,
    "demo_policy_administrator": 6,
}

INSTITUTION_DRAFT = "DEMO-INSTITUTION-DRAFT-001"
VERIFIED_CASE = "DEMO-VERIFICATION-COMPLETE-001"


def _seed_demo_directory_and_accounts() -> None:
    codes = {f"PUBLIC-DEMO-{index:03d}" for index in range(1, len(INSTITUTIONS) + 1)}
    with SessionLocal() as db:
        unexpected_users = db.scalars(
            select(User.username).where(User.username.not_in(tuple(DEMO_ROLES)))
        ).all()
        if unexpected_users:
            raise RuntimeError("Refusing to seed public demo data into a database with non-demo users.")

        unexpected_institutions = db.scalars(
            select(Institution.code).where(Institution.code.not_in(codes))
        ).all()
        if unexpected_institutions:
            raise RuntimeError("Refusing to seed public demo data into a database with non-demo institutions.")

        unexpected_fdrs = db.scalars(
            select(Fdr.identifier).where(~Fdr.identifier.like("DEMO-%"))
        ).all()
        if unexpected_fdrs:
            raise RuntimeError("Refusing to seed public demo data into a database with non-demo FDRs.")

        for index, name in enumerate(INSTITUTIONS, start=1):
            code = f"PUBLIC-DEMO-{index:03d}"
            if not db.scalar(select(Institution.id).where(Institution.code == code)):
                db.add(Institution(
                    name=name,
                    code=code,
                    address="Synthetic public demonstration record",
                    district="Demo District",
                    state="Demo State",
                    institution_type="Demo Institute",
                ))
        db.flush()

        password_hash = pwd_context.hash(PUBLIC_DEMO_PASSWORD)
        admin_id = None
        for username, role in DEMO_ROLES.items():
            account = db.scalar(select(User).where(User.username == username))
            if account is None:
                account = User(
                    username=username,
                    email=f"{username}@public-demo.example.test",
                    password_hash=password_hash,
                    role=role,
                    active=True,
                )
                db.add(account)
                db.flush()
            elif account.role != role or not account.active:
                raise RuntimeError(f"Public demo account {username} has an unexpected role or inactive status.")

            if role == Role.admin:
                admin_id = account.id

            institution_number = ROLE_INSTITUTIONS.get(username)
            if institution_number is not None:
                institution_code = f"PUBLIC-DEMO-{institution_number:03d}"
                institution = db.scalar(select(Institution).where(Institution.code == institution_code))
                memberships = db.scalars(
                    select(UserInstitutionMembership).where(UserInstitutionMembership.user_id == account.id)
                ).all()
                if any(membership.institution_id != institution.id for membership in memberships):
                    raise RuntimeError(f"Public demo account {username} has out-of-scope institution access.")
                if not memberships:
                    db.add(UserInstitutionMembership(
                        user_id=account.id,
                        institution_id=institution.id,
                    ))

        db.commit()
        if admin_id is None:
            raise RuntimeError("Could not initialize the public demo administrator.")


def _seed_role_examples() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "demo_administrator"))
        institution_user = db.scalar(select(User).where(User.username == "demo_institution_user"))
        verification_officer = db.scalar(select(User).where(User.username == "demo_verification_officer"))
        institution = db.scalar(select(Institution).where(Institution.code == "PUBLIC-DEMO-001"))
        verification_institution = db.scalar(select(Institution).where(Institution.code == "PUBLIC-DEMO-003"))
        policy_institution = db.scalar(select(Institution).where(Institution.code == "PUBLIC-DEMO-006"))
        if not all((admin, institution_user, verification_officer, institution, verification_institution, policy_institution)):
            raise RuntimeError("Public demo accounts and institutions must be seeded before role examples.")

        if not db.scalar(select(Fdr.id).where(Fdr.identifier == INSTITUTION_DRAFT)):
            fdr = Fdr(
                identifier=INSTITUTION_DRAFT,
                institution_id=institution.id,
                holder_name=institution.name,
                amount=1_250_000,
                approval_case_reference="PUBLIC-DEMO-INSTITUTION-001",
                bank_name="State Bank of India",
                branch_name="Academic District Branch",
                ifsc_code="DEMO0001023",
                amount_in_words="Rupees twelve lakh fifty thousand only",
                issue_date=now - timedelta(days=30),
                beneficiary="AICTE / Designated Authority",
                joint_holder=institution.name,
                lien_endorsed=True,
                lien_clause="Synthetic demo-only example; not bank evidence.",
                maturity_date=now + timedelta(days=330),
                status=FdrStatus.draft,
                created_by=institution_user.id,
            )
            db.add(fdr)
            db.flush()
            db.add(InstrumentVersion(
                fdr_id=fdr.id,
                version_number=1,
                change_reason="Synthetic public demo sample",
                snapshot=INSTITUTION_DRAFT,
                created_by=institution_user.id,
            ))
            db.add(LifecycleEvent(
                fdr_id=fdr.id,
                from_status="",
                to_status=FdrStatus.draft.value,
                reason="Synthetic sample for the institution-user workflow.",
                actor_id=institution_user.id,
            ))
            db.add(FieldProvenance(
                fdr_id=fdr.id,
                field_name="amount",
                value="1250000",
                level=ProvenanceLevel.declared,
                evidence_reference="Synthetic public demo data",
            ))

        verified = db.scalar(select(Fdr).where(Fdr.identifier == VERIFIED_CASE))
        if verified is None:
            verified = Fdr(
                identifier=VERIFIED_CASE,
                institution_id=verification_institution.id,
                holder_name=verification_institution.name,
                amount=2_250_000,
                approval_case_reference="PUBLIC-DEMO-VERIFICATION-003",
                bank_name="Bank of Baroda",
                branch_name="Technical Park Branch",
                ifsc_code="DEMO0002034",
                amount_in_words="Rupees twenty-two lakh fifty thousand only",
                issue_date=now - timedelta(days=75),
                beneficiary="AICTE / Designated Authority",
                joint_holder=verification_institution.name,
                lien_endorsed=True,
                lien_clause="Synthetic demo-only example; not bank evidence.",
                maturity_date=now + timedelta(days=255),
                status=FdrStatus.verified,
                created_by=verification_officer.id,
            )
            db.add(verified)
            db.flush()
            db.add(VerificationCase(
                fdr_id=verified.id,
                status=VerificationStatus.verified,
                assigned_to=verification_officer.id,
                outcome_notes="Synthetic demo: branch confirmation received and instrument fields reconciled.",
                evidence_reference="PUBLIC-DEMO-CONFIRMATION-003",
            ))
            db.add(InstrumentVersion(
                fdr_id=verified.id,
                version_number=1,
                change_reason="Synthetic public demo sample",
                snapshot=VERIFIED_CASE,
                created_by=verification_officer.id,
            ))
            db.add(LifecycleEvent(
                fdr_id=verified.id,
                from_status=FdrStatus.under_review.value,
                to_status=FdrStatus.verified.value,
                reason="Synthetic completed-verification example.",
                actor_id=verification_officer.id,
            ))
            db.add(FieldProvenance(
                fdr_id=verified.id,
                field_name="amount",
                value="2250000",
                level=ProvenanceLevel.declared,
                evidence_reference="Synthetic public demo data",
            ))

        policy_rule = db.scalar(
            select(PolicyRule)
            .where(PolicyRule.active.is_(True))
            .order_by(PolicyRule.id)
        )
        if policy_rule and not db.scalar(
            select(DepositAssessment.id).where(
                DepositAssessment.institution_id == policy_institution.id,
                DepositAssessment.notes == "Synthetic public demo policy assessment.",
            )
        ):
            db.add(DepositAssessment(
                institution_id=policy_institution.id,
                policy_rule_id=policy_rule.id,
                amount=1_500_000,
                status="configured",
                notes="Synthetic public demo policy assessment.",
                created_by=admin.id,
            ))
        db.commit()


def seed_public_demo() -> None:
    _seed_demo_directory_and_accounts()

    from .seed_policies import seed_policies
    from .seed_scenarios import seed_scenarios

    seed_policies()
    seed_scenarios()
    _seed_role_examples()
