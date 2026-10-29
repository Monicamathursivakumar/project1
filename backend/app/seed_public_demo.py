"""Seed role-specific sample data for the shared public demo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import uuid

from PIL import Image, ImageDraw
from sqlalchemy import Column, MetaData, String, Table, insert, select

from .main import (
    AuditEvent,
    DepositAssessment,
    EmployeeVerification,
    FieldProvenance,
    Fdr,
    FdrStatus,
    InstrumentVersion,
    Institution,
    LifecycleEvent,
    PolicyRule,
    ProvenanceLevel,
    RegistrationAuditEvent,
    RegistrationRequest,
    Role,
    SessionLocal,
    settings,
    User,
    UserInstitutionMembership,
    FdrStatus,
    VerificationCase,
    VerificationStatus,
    pwd_context,
)

PUBLIC_DEMO_STATE = Table(
    "public_demo_state",
    MetaData(),
    Column("key", String(64), primary_key=True),
    Column("value", String(255), nullable=False),
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
DEMO_INSTITUTION_TARGET = 3000
DEMO_FDR_TARGET = 438
DEMO_VERIFIED_TARGET = 8
DEMO_ATTENTION_TARGET = 2


def _synthetic_identity_image() -> bytes:
    image = Image.new("RGB", (720, 420), "#eef3f8")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((24, 24, 696, 396), radius=20, fill="#ffffff", outline="#9aabc0", width=3)
    draw.rounded_rectangle((48, 48, 672, 128), radius=12, fill="#17314b")
    draw.text((72, 76), "VAULTTRACE - SAMPLE EVIDENCE", fill="#ffffff")
    draw.text((72, 174), "DEMO SAMPLE DOCUMENT", fill="#17314b")
    draw.text((72, 224), "NOT A REAL IDENTITY CARD", fill="#a4312c")
    draw.text((72, 288), "Synthetic placeholder for reviewer UI testing only.", fill="#52667c")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _seed_registration_samples() -> None:
    now = datetime.now(timezone.utc)
    image_content = _synthetic_identity_image()
    upload_root = Path(settings.upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)
    image_name = "demo-synthetic-identity-placeholder.png"
    image_path = upload_root / image_name
    if not image_path.is_file():
        image_path.write_bytes(image_content)

    sample_requests = (
        {
            "username": "demo_sample_email_review",
            "full_name": "DEMO Applicant - Email Review",
            "email": "email-review@vaulttrace.invalid",
            "account_type": "viewer",
            "organization_name": "",
            "employee_id": None,
            "department": "",
            "designation": "",
            "email_verified_at": None,
            "identity_status": "pending",
            "employee_status": "not_required",
            "institution_status": "not_required",
            "status": "pending_email_verification",
            "created_at": now - timedelta(hours=5),
            "decision_reason": "",
            "rejected": False,
        },
        {
            "username": "demo_sample_identity_review",
            "full_name": "DEMO Applicant - Identity Review",
            "email": "identity-review@vaulttrace.invalid",
            "account_type": "reviewing_officer",
            "organization_name": "VaultTrace Synthetic Demo Office",
            "employee_id": "DEMO-EMPLOYEE-IDENTITY-001",
            "department": "Sample Operations",
            "designation": "Demo Reviewing Officer",
            "email_verified_at": now - timedelta(days=1, hours=2),
            "identity_status": "pending",
            "employee_status": "pending",
            "institution_status": "not_required",
            "status": "pending_identity_verification",
            "created_at": now - timedelta(days=1),
            "decision_reason": "",
            "rejected": False,
        },
        {
            "username": "demo_sample_institution_review",
            "full_name": "DEMO Applicant - Institution Review",
            "email": "institution-review@vaulttrace.invalid",
            "account_type": "institution_user",
            "organization_name": INSTITUTIONS[0],
            "employee_id": None,
            "department": "",
            "designation": "",
            "email_verified_at": now - timedelta(hours=18),
            "identity_status": "pending",
            "employee_status": "not_required",
            "institution_status": "pending",
            "status": "pending_identity_verification",
            "created_at": now - timedelta(hours=20),
            "decision_reason": "",
            "rejected": False,
        },
        {
            "username": "demo_sample_closed_request",
            "full_name": "DEMO Applicant - Closed Example",
            "email": "closed-example@vaulttrace.invalid",
            "account_type": "viewer",
            "organization_name": "",
            "employee_id": None,
            "department": "",
            "designation": "",
            "email_verified_at": None,
            "identity_status": "pending",
            "employee_status": "not_required",
            "institution_status": "not_required",
            "status": "rejected",
            "created_at": now - timedelta(days=3),
            "decision_reason": "Synthetic example only; no real applicant or eligibility decision.",
            "rejected": True,
        },
    )

    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "demo_administrator"))
        institution = db.scalar(select(Institution).where(Institution.code == "PUBLIC-DEMO-001"))
        password_hash = pwd_context.hash(PUBLIC_DEMO_PASSWORD)
        for sample in sample_requests:
            existing = db.scalar(
                select(RegistrationRequest).where(
                    RegistrationRequest.username == sample["username"]
                )
            )
            request_email_exists = db.scalar(
                select(RegistrationRequest.id).where(
                    RegistrationRequest.email == sample["email"]
                )
            )
            user_exists = db.scalar(
                select(User.id).where(
                    (User.username == sample["username"]) | (User.email == sample["email"])
                )
            )
            if existing is not None or request_email_exists or user_exists:
                continue
            account_type = sample["account_type"]
            institution_id = institution.id if account_type == "institution_user" and institution else None
            created_at = sample["created_at"]
            request = RegistrationRequest(
                public_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"vaulttrace:{sample['username']}")),
                username=sample["username"],
                full_name=sample["full_name"],
                email=sample["email"],
                password_hash=password_hash,
                account_type=account_type,
                organization_name=sample["organization_name"],
                institution_id=institution_id,
                employee_id=sample["employee_id"],
                department=sample["department"],
                designation=sample["designation"],
                email_verified_at=sample["email_verified_at"],
                identity_status=sample["identity_status"],
                employee_status=sample["employee_status"],
                institution_status=sample["institution_status"],
                role_status="pending",
                status=sample["status"],
                identity_document_stored_name=image_name,
                identity_document_sha256=sha256(image_content).hexdigest(),
                identity_document_content_type="image/png",
                identity_document_size=len(image_content),
                identity_document_uploaded_at=created_at,
                decision_reason=sample["decision_reason"],
                decision_actor_id=admin.id if sample["rejected"] and admin else None,
                decision_at=created_at if sample["rejected"] else None,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(request)
            db.flush()
            if request.employee_id:
                db.add(EmployeeVerification(
                    registration_id=request.id,
                    employee_id=request.employee_id,
                    full_name=request.full_name,
                    official_email=request.email,
                    organization_name=request.organization_name,
                    department=request.department,
                    designation=request.designation,
                    requested_role=request.account_type,
                    status=request.employee_status,
                ))
            db.add(RegistrationAuditEvent(
                registration_id=request.id,
                actor_id=admin.id if sample["rejected"] and admin else None,
                action="reject" if sample["rejected"] else "demo_sample_created",
                previous_status="pending_email_verification" if sample["rejected"] else "",
                new_status=request.status,
                reason=sample["decision_reason"] or "Synthetic sample request for demonstrating account review.",
                created_at=created_at,
            ))
        db.commit()


def _seed_dashboard_volume() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "demo_administrator"))
        if admin is None:
            raise RuntimeError("The public demo administrator must exist before dashboard data is seeded.")

        institution_count = db.query(Institution).count()
        missing_institutions = max(0, DEMO_INSTITUTION_TARGET - institution_count)
        institutions = db.scalars(select(Institution).order_by(Institution.id)).all()
        institutions_by_code = {item.code for item in institutions}
        next_institution_number = 1
        while missing_institutions:
            code = f"PUBLIC-DEMO-VOLUME-{next_institution_number:04d}"
            next_institution_number += 1
            if code in institutions_by_code:
                continue
            institution = Institution(
                name=f"Synthetic Demo Institution {next_institution_number - 1:04d}",
                code=code,
                address="Synthetic sample record for public demo dashboard volume.",
                district="Synthetic Demo District",
                state="Synthetic Demo Region",
                institution_type="Synthetic Demo Institution",
            )
            db.add(institution)
            institutions.append(institution)
            institutions_by_code.add(code)
            missing_institutions -= 1
        db.flush()

        fdr_count = db.query(Fdr).count()
        verified_count = db.query(Fdr).filter(Fdr.status == FdrStatus.verified).count()
        attention_count = db.query(Fdr).filter(
            Fdr.status.in_([FdrStatus.submitted, FdrStatus.under_review])
        ).count()
        verified_to_add = max(0, DEMO_VERIFIED_TARGET - verified_count)
        attention_to_add = max(0, DEMO_ATTENTION_TARGET - attention_count)
        missing_fdrs = max(
            DEMO_FDR_TARGET - fdr_count,
            verified_to_add + attention_to_add,
            0,
        )
        existing_volume_ids = set(db.scalars(
            select(Fdr.identifier).where(Fdr.identifier.like("DEMO-VOLUME-%"))
        ).all())
        next_fdr_number = 1
        verification_officer = db.scalar(
            select(User).where(User.username == "demo_verification_officer")
        )
        added = 0
        verified_added = 0
        attention_added = 0
        while added < missing_fdrs:
            identifier = f"DEMO-VOLUME-{next_fdr_number:04d}"
            next_fdr_number += 1
            if identifier in existing_volume_ids:
                continue
            institution = institutions[(next_fdr_number - 2) % len(institutions)]
            if verified_added < verified_to_add:
                status = FdrStatus.verified
                verified_added += 1
            elif attention_added < attention_to_add:
                status = FdrStatus.under_review if attention_added % 2 else FdrStatus.submitted
                attention_added += 1
            else:
                status = FdrStatus.draft
            amount = 500_000 + (next_fdr_number % 20) * 50_000
            fdr = Fdr(
                identifier=identifier,
                institution_id=institution.id,
                holder_name=institution.name,
                amount=amount,
                approval_case_reference=f"DEMO-VOLUME-CASE-{next_fdr_number:04d}",
                bank_name="Synthetic Demo Bank",
                branch_name="Synthetic Demo Branch",
                ifsc_code=f"DEMO0{next_fdr_number:06d}"[-11:],
                amount_in_words=f"Synthetic demo amount {amount} only",
                issue_date=now - timedelta(days=365),
                beneficiary="Synthetic Demo Beneficiary",
                joint_holder=institution.name,
                lien_endorsed=True,
                lien_clause="Synthetic demo data; not bank evidence.",
                maturity_date=now + timedelta(days=30 + next_fdr_number % 330),
                status=status,
                created_by=admin.id,
            )
            db.add(fdr)
            db.flush()
            db.add(InstrumentVersion(
                fdr_id=fdr.id,
                version_number=1,
                change_reason="Synthetic public demo volume sample",
                snapshot=identifier,
                created_by=admin.id,
            ))
            db.add(LifecycleEvent(
                fdr_id=fdr.id,
                from_status="",
                to_status=status.value,
                reason="Synthetic sample record for dashboard and registry demonstrations.",
                actor_id=admin.id,
            ))
            db.add(FieldProvenance(
                fdr_id=fdr.id,
                field_name="amount",
                value=str(amount),
                level=ProvenanceLevel.declared,
                evidence_reference="Synthetic public demo data; not bank evidence.",
            ))
            if status == FdrStatus.verified:
                db.add(VerificationCase(
                    fdr_id=fdr.id,
                    status=VerificationStatus.verified,
                    assigned_to=verification_officer.id if verification_officer else admin.id,
                    outcome_notes="Synthetic verified-status example for dashboard demonstration; no real bank verification.",
                    evidence_reference=f"DEMO-SYNTHETIC-{next_fdr_number:04d}",
                ))
            elif status in {FdrStatus.submitted, FdrStatus.under_review}:
                db.add(VerificationCase(
                    fdr_id=fdr.id,
                    status=VerificationStatus.in_review if status == FdrStatus.under_review else VerificationStatus.pending,
                    assigned_to=verification_officer.id if verification_officer else None,
                    outcome_notes="Synthetic pending verification example for dashboard demonstration.",
                    evidence_reference="",
                ))
            db.add(AuditEvent(
                actor_id=admin.id,
                action="scenario_seeded",
                entity="fdr",
                entity_id=str(fdr.id),
                details="Synthetic public demo volume record; not a real financial instrument.",
            ))
            existing_volume_ids.add(identifier)
            added += 1
        db.commit()


def _seed_demo_directory_and_accounts() -> None:
    codes = {f"PUBLIC-DEMO-{index:03d}" for index in range(1, len(INSTITUTIONS) + 1)}
    with SessionLocal() as db:
        PUBLIC_DEMO_STATE.create(bind=db.get_bind(), checkfirst=True)
        initialized = db.execute(
            select(PUBLIC_DEMO_STATE.c.value).where(PUBLIC_DEMO_STATE.c.key == "initialized")
        ).scalar_one_or_none()
        if initialized is None:
            unexpected_users = db.scalars(
                select(User.username).where(User.username.not_in(tuple(DEMO_ROLES)))
            ).all()
            if unexpected_users:
                raise RuntimeError("Refusing to seed public demo data into a database with non-demo users.")

            unexpected_institutions = db.scalars(
                select(Institution.code).where(
                    Institution.code.not_in(codes),
                    ~Institution.code.like("PUBLIC-DEMO-VOLUME-%"),
                )
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
    _seed_registration_samples()
    _seed_dashboard_volume()
    with SessionLocal() as db:
        if db.execute(
            select(PUBLIC_DEMO_STATE.c.key).where(PUBLIC_DEMO_STATE.c.key == "initialized")
        ).scalar_one_or_none() is None:
            db.execute(insert(PUBLIC_DEMO_STATE).values(key="initialized", value="true"))
            db.commit()
