"""Seed role-specific sample data for the shared public demo."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import uuid

from PIL import Image, ImageDraw
from sqlalchemy import Column, MetaData, String, Table, func, insert, select

from .main import (
    AuditEvent,
    CustodyEvent,
    DepositAssessment,
    Discrepancy,
    DiscrepancyStatus,
    EmployeeVerification,
    FieldProvenance,
    Fdr,
    FdrStatus,
    InstrumentVersion,
    Institution,
    InstitutionProgramme,
    LifecycleEvent,
    PolicyRule,
    ProvenanceLevel,
    ReleaseRequest,
    ReleaseType,
    RegistrationAuditEvent,
    RegistrationRequest,
    Role,
    SessionLocal,
    User,
    UserInstitutionMembership,
    VerificationCase,
    VerificationStatus,
    pwd_context,
    settings,
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
DEMO_STATUS_TARGETS = {
    FdrStatus.verified: 348,
    FdrStatus.under_review: 36,
    FdrStatus.submitted: 13,
    FdrStatus.draft: 41,
}
DEMO_PROGRAMME_OFFERINGS = {
    "PUBLIC-DEMO-001": (
        ("Engineering", "Undergraduate", "Computer Science and Engineering", "Full-time", "Morning", "Available", "120", "108", "82%"),
        ("Engineering", "Undergraduate", "Electrical Engineering", "Full-time", "Morning", "Available", "90", "76", "78%"),
        ("Engineering", "Postgraduate", "Structural Engineering", "Full-time", "Evening", "Available", "36", "29", "86%"),
    ),
    "PUBLIC-DEMO-002": (
        ("Diploma", "Diploma", "Mechanical Engineering", "Full-time", "Morning", "Available", "60", "54", "74%"),
        ("Diploma", "Diploma", "Computer Engineering", "Full-time", "Afternoon", "Available", "60", "51", "81%"),
        ("Diploma", "Diploma", "Civil Engineering", "Part-time", "Evening", "Limited", "40", "32", "69%"),
    ),
    "PUBLIC-DEMO-003": (
        ("Science", "Undergraduate", "Data Science", "Full-time", "Morning", "Available", "80", "72", "77%"),
        ("Computer Applications", "Undergraduate", "Bachelor of Computer Applications", "Full-time", "Morning", "Available", "100", "91", "79%"),
        ("Computer Applications", "Postgraduate", "Master of Computer Applications", "Full-time", "Evening", "Available", "50", "43", "84%"),
    ),
    "PUBLIC-DEMO-004": (
        ("Technology", "Undergraduate", "Artificial Intelligence", "Full-time", "Morning", "Available", "90", "84", "88%"),
        ("Technology", "Undergraduate", "Information Systems", "Full-time", "Afternoon", "Available", "75", "66", "80%"),
        ("Technology", "Postgraduate", "Cybersecurity", "Part-time", "Evening", "Limited", "40", "34", "91%"),
    ),
    "PUBLIC-DEMO-005": (
        ("Design", "Undergraduate", "Communication Design", "Full-time", "Morning", "Available", "60", "56", "83%"),
        ("Design", "Undergraduate", "Product Design", "Full-time", "Afternoon", "Available", "45", "39", "79%"),
        ("Design", "Postgraduate", "User Experience Design", "Part-time", "Evening", "Limited", "30", "26", "87%"),
    ),
    "PUBLIC-DEMO-006": (
        ("Management", "Undergraduate", "Business Administration", "Full-time", "Morning", "Available", "120", "112", "76%"),
        ("Commerce", "Undergraduate", "Commerce", "Full-time", "Afternoon", "Available", "100", "88", "72%"),
        ("Management", "Postgraduate", "Business Administration", "Full-time", "Evening", "Available", "60", "55", "89%"),
    ),
}


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
        PUBLIC_DEMO_STATE.create(bind=db.get_bind(), checkfirst=True)
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

        distribution_key = "dashboard_status_distribution_v2"
        distribution_initialized = db.execute(
            select(PUBLIC_DEMO_STATE.c.value).where(PUBLIC_DEMO_STATE.c.key == distribution_key)
        ).scalar_one_or_none()
        if distribution_initialized is not None:
            db.commit()
            return

        scenario_examples = db.scalars(
            select(Fdr).where(Fdr.identifier.in_(("DEMO-FDR-004", "DEMO-FDR-005")))
        ).all()
        for fdr in scenario_examples:
            if fdr.status in {FdrStatus.release_requested, FdrStatus.closed}:
                previous_status = fdr.status.value
                fdr.status = FdrStatus.draft
                db.add(LifecycleEvent(
                    fdr_id=fdr.id,
                    from_status=previous_status,
                    to_status=FdrStatus.draft.value,
                    reason="Synthetic dashboard sample distribution update.",
                    actor_id=admin.id,
                ))
                if fdr.identifier == "DEMO-FDR-004":
                    release_request = db.scalar(
                        select(ReleaseRequest).where(
                            ReleaseRequest.fdr_id == fdr.id,
                            ReleaseRequest.status == "pending",
                        )
                    )
                    if release_request:
                        release_request.status = "cancelled"
                        release_request.decision_notes = "Cancelled when updating the synthetic dashboard status distribution."
                    verification_case = db.scalar(
                        select(VerificationCase).where(VerificationCase.fdr_id == fdr.id)
                    )
                    if verification_case:
                        verification_case.status = VerificationStatus.pending
                        verification_case.evidence_reference = ""
                        verification_case.outcome_notes = "Synthetic demo case returned to a pending state."

        db.flush()
        volume_rows = db.scalars(
            select(Fdr).where(Fdr.identifier.like("DEMO-VOLUME-%")).order_by(Fdr.identifier)
        ).all()
        base_rows = db.scalars(
            select(Fdr).where(~Fdr.identifier.like("DEMO-VOLUME-%"))
        ).all()
        base_counts = {status: 0 for status in DEMO_STATUS_TARGETS}
        for fdr in base_rows:
            if fdr.status in base_counts:
                base_counts[fdr.status] += 1
        volume_targets = {
            status: max(0, target - base_counts[status])
            for status, target in DEMO_STATUS_TARGETS.items()
        }
        base_count = len(base_rows)
        target_volume_count = max(
            DEMO_FDR_TARGET - base_count,
            sum(volume_targets.values()),
            0,
        )

        next_fdr_number = 1
        verification_officer = db.scalar(
            select(User).where(User.username == "demo_verification_officer")
        )
        existing_volume_ids = {fdr.identifier for fdr in volume_rows}
        while len(volume_rows) < target_volume_count:
            identifier = f"DEMO-VOLUME-{next_fdr_number:04d}"
            next_fdr_number += 1
            if identifier in existing_volume_ids:
                continue
            institution = institutions[(next_fdr_number - 2) % len(institutions)]
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
                status=FdrStatus.draft,
                created_by=admin.id,
            )
            db.add(fdr)
            db.flush()
            volume_rows.append(fdr)
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
                to_status=FdrStatus.draft.value,
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
            db.add(AuditEvent(
                actor_id=admin.id,
                action="scenario_seeded",
                entity="fdr",
                entity_id=str(fdr.id),
                details="Synthetic public demo volume record; not a real financial instrument.",
            ))
            existing_volume_ids.add(identifier)

        assigned_statuses = [
            status
            for status, count in volume_targets.items()
            for _ in range(count)
        ]
        assigned_statuses.extend(
            [FdrStatus.draft] * max(0, len(volume_rows) - len(assigned_statuses))
        )
        for fdr, status in zip(volume_rows, assigned_statuses):
            previous_status = fdr.status
            fdr.status = status
            if previous_status != status:
                db.add(LifecycleEvent(
                    fdr_id=fdr.id,
                    from_status=previous_status.value,
                    to_status=status.value,
                    reason="Synthetic dashboard sample distribution update.",
                    actor_id=admin.id,
                ))
            if status in {FdrStatus.verified, FdrStatus.under_review, FdrStatus.submitted}:
                verification_case = db.scalar(
                    select(VerificationCase).where(VerificationCase.fdr_id == fdr.id)
                )
                verification_status = {
                    FdrStatus.verified: VerificationStatus.verified,
                    FdrStatus.under_review: VerificationStatus.in_review,
                    FdrStatus.submitted: VerificationStatus.pending,
                }[status]
                if verification_case is None:
                    verification_case = VerificationCase(fdr_id=fdr.id)
                    db.add(verification_case)
                verification_case.status = verification_status
                verification_case.assigned_to = verification_officer.id if verification_officer else None
                verification_case.outcome_notes = (
                    "Synthetic verified-status example for dashboard demonstration; no real bank verification."
                    if status == FdrStatus.verified
                    else "Synthetic pending verification example for dashboard demonstration."
                )
                verification_case.evidence_reference = (
                    f"DEMO-SYNTHETIC-{fdr.identifier.rsplit('-', 1)[-1]}"
                    if status == FdrStatus.verified
                    else ""
                )

        db.execute(insert(PUBLIC_DEMO_STATE).values(key=distribution_key, value="true"))
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

        _seed_demo_programmes(db)

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


def _seed_demo_programmes(db) -> None:
    institutions = {
        institution.code: institution
        for institution in db.scalars(
            select(Institution).where(Institution.code.in_(DEMO_PROGRAMME_OFFERINGS))
        )
    }
    if len(institutions) != len(DEMO_PROGRAMME_OFFERINGS):
        raise RuntimeError("All role-linked public demo institutions must exist before programme seeding.")

    existing = set(db.execute(
        select(
            InstitutionProgramme.institution_id,
            InstitutionProgramme.programme,
            InstitutionProgramme.level,
            InstitutionProgramme.course,
        )
    ).all())
    for code, offerings in DEMO_PROGRAMME_OFFERINGS.items():
        institution = institutions[code]
        for programme, level, course, course_type, shift, availability, intake, enrollment, placement in offerings:
            offering_key = (institution.id, programme, level, course)
            if offering_key in existing:
                continue
            db.add(InstitutionProgramme(
                institution_id=institution.id,
                programme=programme,
                level=level,
                course=course,
                course_type=course_type,
                shift=shift,
                availability=availability,
                intake=intake,
                enrollment=enrollment,
                placement=placement,
            ))
            existing.add(offering_key)


def _seed_role_dashboard_metrics() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        PUBLIC_DEMO_STATE.create(bind=db.get_bind(), checkfirst=True)
        state_key = "role_dashboard_samples_v1"
        if db.execute(
            select(PUBLIC_DEMO_STATE.c.value).where(PUBLIC_DEMO_STATE.c.key == state_key)
        ).scalar_one_or_none() is not None:
            return

        roles = {
            username: db.scalar(select(User).where(User.username == username))
            for username in (
                "demo_administrator",
                "demo_auditor",
                "demo_institution_user",
                "demo_reviewing_officer",
                "demo_verification_officer",
                "demo_custody_officer",
            )
        }
        audit_institutions = db.scalars(
            select(Institution).order_by(Institution.id).limit(23)
        ).all()
        if any(user is None for user in roles.values()) or len(audit_institutions) != 23:
            raise RuntimeError("Demo roles and 23 institutions must exist before role dashboard samples.")

        reviewer = roles["demo_reviewing_officer"]
        verifier = roles["demo_verification_officer"]
        custodian = roles["demo_custody_officer"]
        auditor = roles["demo_auditor"]
        role_institution = db.scalar(
            select(Institution).where(Institution.code == "PUBLIC-DEMO-001")
        )
        fdrs = db.scalars(select(Fdr).order_by(Fdr.identifier)).all()
        volume_fdrs = [fdr for fdr in fdrs if fdr.identifier.startswith("DEMO-VOLUME-")]
        if len(volume_fdrs) < 347:
            raise RuntimeError("Dashboard volume FDRs must be seeded before role dashboard samples.")

        institution_rows = db.scalars(
            select(Fdr)
            .where(Fdr.institution_id == role_institution.id)
            .order_by(Fdr.identifier)
        ).all()
        institution_fdrs = [
            fdr for fdr in institution_rows
            if fdr.identifier.startswith(("DEMO-FDR-", "DEMO-INSTITUTION-DRAFT-", "DEMO-VOLUME-"))
        ]
        institution_status_targets = {
            FdrStatus.draft: 3,
            FdrStatus.verified: 7,
            FdrStatus.under_review: 2,
        }
        institution_status_counts = {status: 0 for status in institution_status_targets}
        institution_samples: list[Fdr] = []
        for fdr in institution_fdrs[:12]:
            if fdr.status in institution_status_targets and institution_status_counts[fdr.status] < institution_status_targets[fdr.status]:
                institution_samples.append(fdr)
                institution_status_counts[fdr.status] += 1
                continue
            needed_status = next(
                status for status, target in institution_status_targets.items()
                if institution_status_counts[status] < target
            )
            previous = fdr.status
            fdr.status = needed_status
            db.add(LifecycleEvent(
                fdr_id=fdr.id,
                from_status=previous.value,
                to_status=needed_status.value,
                reason="Synthetic role dashboard sample status.",
                actor_id=roles["demo_administrator"].id,
            ))
            institution_samples.append(fdr)
            institution_status_counts[needed_status] += 1
        for status, target in institution_status_targets.items():
            missing = target - institution_status_counts[status]
            donors = [
                fdr for fdr in volume_fdrs
                if fdr not in institution_samples
                and fdr.institution_id != role_institution.id
                and fdr.status == status
            ][:missing]
            if len(donors) != missing:
                raise RuntimeError(f"Not enough synthetic {status.value} FDRs for institution role samples.")
            for fdr in donors:
                fdr.institution_id = role_institution.id
                fdr.holder_name = role_institution.name
                institution_samples.append(fdr)
        if len(institution_samples) != 12:
            raise RuntimeError("The institution role dashboard sample did not reach 12 FDRs.")
        for fdr in institution_samples:
            db.add(AuditEvent(
                actor_id=roles["demo_institution_user"].id,
                action="demo_role_institution_sample",
                entity="fdr",
                entity_id=fdr.identifier,
                details="Synthetic institution-user dashboard sample.",
            ))
        returned_samples = [
            fdr for fdr in institution_samples
            if fdr.status == FdrStatus.under_review
        ]
        for index, fdr in enumerate(returned_samples, start=1):
            rule_id = f"DEMO-ROLE-INSTITUTION-RETURN-{index:02d}"
            if not db.scalar(select(Discrepancy.id).where(Discrepancy.rule_id == rule_id)):
                db.add(Discrepancy(
                    fdr_id=fdr.id,
                    rule_id=rule_id,
                    severity="medium",
                    explanation="Synthetic sample returned for correction; update the declared record before resubmission.",
                    expected_value="Complete and consistent declaration",
                    observed_value="Correction requested",
                    status=DiscrepancyStatus.open,
                ))

        verification_statuses = (
            [VerificationStatus.verified] * 259
            + [VerificationStatus.pending] * 60
            + [VerificationStatus.rejected] * 28
        )
        selected_verification_ids = {fdr.id for fdr in volume_fdrs[:347]}
        for fdr, status in zip(volume_fdrs[:347], verification_statuses):
            case = db.scalar(select(VerificationCase).where(VerificationCase.fdr_id == fdr.id))
            if case is None:
                case = VerificationCase(fdr_id=fdr.id)
                db.add(case)
            case.status = status
            case.assigned_to = verifier.id
            case.outcome_notes = "Synthetic verification-role dashboard sample; no real bank confirmation."
            case.evidence_reference = f"DEMO-ROLE-VERIFICATION-{fdr.identifier.rsplit('-', 1)[-1]}"
        for case in db.scalars(
            select(VerificationCase).where(VerificationCase.assigned_to == verifier.id)
        ):
            if case.fdr_id not in selected_verification_ids:
                case.assigned_to = None

        reviewer_institution = db.scalar(
            select(Institution).where(Institution.code == "PUBLIC-DEMO-002")
        )
        reviewer_fdrs = db.scalars(
            select(Fdr)
            .where(Fdr.institution_id == reviewer_institution.id)
            .order_by(Fdr.identifier)
        ).all()
        if not reviewer_fdrs:
            raise RuntimeError("The reviewer sample institution must have at least one FDR.")
        for index in range(1, 46):
            finding_id = (
                f"DEMO-ROLE-REVIEW-AUDIT-{index:02d}"
                if index <= 6
                else f"DEMO-ROLE-REVIEW-{index:02d}"
            )
            if db.scalar(select(Discrepancy.id).where(Discrepancy.rule_id == finding_id)):
                continue
            resolved = index > 28
            db.add(Discrepancy(
                fdr_id=reviewer_fdrs[(index - 1) % len(reviewer_fdrs)].id,
                rule_id=finding_id,
                severity="high" if index % 4 == 0 else "medium",
                explanation=(
                    "Synthetic auditor sample finding for review dashboard."
                    if index <= 6
                    else "Synthetic reviewer workflow sample; not a real institutional finding."
                ),
                expected_value="Declared value matches supporting evidence",
                observed_value=f"Synthetic discrepancy sample {index:02d}",
                status=DiscrepancyStatus.resolved if resolved else DiscrepancyStatus.open,
                resolution_notes="Synthetic sample marked resolved." if resolved else "",
                resolved_by=reviewer.id if resolved else None,
            ))

        for fdr in volume_fdrs[:214]:
            evidence_reference = f"DEMO-ROLE-CUSTODY-{fdr.id}"
            if not db.scalar(
                select(CustodyEvent.id).where(
                    CustodyEvent.actor_id == custodian.id,
                    CustodyEvent.evidence_reference == evidence_reference,
                )
            ):
                db.add(CustodyEvent(
                    fdr_id=fdr.id,
                    event_type="received",
                    location=f"Demo Vault / Cabinet {(fdr.id % 12) + 1:02d}",
                    custodian="Synthetic Demo Custody Officer",
                    evidence_reference=evidence_reference,
                    remarks="Synthetic custody dashboard sample; no physical instrument is represented.",
                    actor_id=custodian.id,
                ))
        for fdr in volume_fdrs[:12]:
            evidence_reference = f"DEMO-ROLE-HANDOVER-{fdr.id}"
            if not db.scalar(
                select(CustodyEvent.id).where(
                    CustodyEvent.actor_id == custodian.id,
                    CustodyEvent.evidence_reference == evidence_reference,
                )
            ):
                db.add(CustodyEvent(
                    fdr_id=fdr.id,
                    event_type="handover_pending",
                    location=f"Demo Vault / Handover Desk {(fdr.id % 4) + 1}",
                    custodian="Synthetic Demo Custody Officer",
                    evidence_reference=evidence_reference,
                    remarks="Synthetic pending handover sample.",
                    actor_id=custodian.id,
                ))
        for index, fdr in enumerate(volume_fdrs[:8], start=1):
            reason = f"DEMO-ROLE-CUSTODY-RELEASE-{index:02d}: Synthetic release request sample."
            if not db.scalar(select(ReleaseRequest.id).where(ReleaseRequest.reason == reason)):
                db.add(ReleaseRequest(
                    fdr_id=fdr.id,
                    request_type=ReleaseType.release,
                    reason=reason,
                    status="pending",
                    requested_by=custodian.id,
                ))

        document_categories = (
            "Security Deposit FDR",
            "Institution Registration",
            "Bank Confirmation",
            "Lien Endorsement",
            "Board Resolution",
            "Renewal Evidence",
            "Release Clearance",
            "Identity Proof",
        )
        policy_creator = roles["demo_administrator"]
        for index in range(18):
            rule_id = f"DEMO-ROLE-POLICY-{index + 1:02d}"
            if db.scalar(select(PolicyRule.id).where(PolicyRule.rule_id == rule_id)):
                continue
            required_documents = [
                document_categories[index % len(document_categories)],
                document_categories[(index + 1) % len(document_categories)],
            ]
            db.add(PolicyRule(
                rule_id=rule_id,
                description=f"Synthetic active validation rule {index + 1:02d} for role dashboard samples.",
                required_documents=json.dumps(required_documents),
                amount_floor=100_000 + index * 25_000,
                effective_date=now - timedelta(days=30),
                expiry_date=now + timedelta(days=365),
                version=1,
                active=True,
                source_reference="Synthetic public demo policy; not regulatory guidance.",
                created_by=policy_creator.id,
            ))

        existing_audit_count = db.scalar(
            select(func.count(AuditEvent.id)).where(AuditEvent.action == "demo_audit_review")
        ) or 0
        for index in range(existing_audit_count, 542):
            institution = audit_institutions[index % len(audit_institutions)]
            db.add(AuditEvent(
                actor_id=auditor.id,
                action="demo_audit_review",
                entity="institution",
                entity_id=str(institution.id),
                details=(
                    f"DEMO-ROLE-DASHBOARD-AUDIT-{index + 1:03d}: Synthetic audit trail sample."
                ),
                created_at=now - timedelta(minutes=index),
            ))

        db.execute(
            insert(PUBLIC_DEMO_STATE).values(key=state_key, value="true")
        )
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
    _seed_role_dashboard_metrics()
    with SessionLocal() as db:
        if db.execute(
            select(PUBLIC_DEMO_STATE.c.key).where(PUBLIC_DEMO_STATE.c.key == "initialized")
        ).scalar_one_or_none() is None:
            db.execute(insert(PUBLIC_DEMO_STATE).values(key="initialized", value="true"))
            db.commit()
