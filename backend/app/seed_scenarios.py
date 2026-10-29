"""Create linked demo workflow records for exercising every VaultTrace page."""

from __future__ import annotations

import argparse
import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from .main import (
    AuditEvent,
    CustodyEvent,
    DepositAssessment,
    Discrepancy,
    DiscrepancyStatus,
    Document,
    Fdr,
    FdrStatus,
    FieldProvenance,
    InstrumentVersion,
    Institution,
    LifecycleEvent,
    NotificationEvent,
    PolicyRule,
    ProvenanceLevel,
    ReleaseRequest,
    ReleaseType,
    SessionLocal,
    User,
    VerificationCase,
    VerificationStatus,
    engine,
    settings,
)


def seed_scenarios() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        institutions = db.scalars(select(Institution).order_by(Institution.id).limit(6)).all()
        if not user or len(institutions) < 3:
            raise RuntimeError("The administrator and institution catalogue must be loaded first")
        existing = db.scalars(select(Fdr.identifier).where(Fdr.identifier.like("DEMO-FDR-%"))).all()
        if existing:
            return 0

        policies = db.scalars(select(PolicyRule).where(PolicyRule.active.is_(True)).order_by(PolicyRule.id)).all()
        created = 0
        scenarios = [
            ("DEMO-FDR-001", institutions[0], 3500000, FdrStatus.verified, 45, "State Bank of India", "Verification complete; eligible for controlled lifecycle actions."),
            ("DEMO-FDR-002", institutions[1], 1500000, FdrStatus.under_review, 75, "Bank of Baroda", "Awaiting independent branch confirmation."),
            ("DEMO-FDR-003", institutions[2], 500000, FdrStatus.submitted, 12, "Punjab National Bank", "Submitted by institution; evidence review pending."),
            ("DEMO-FDR-004", institutions[3], 1500000, FdrStatus.release_requested, -8, "Canara Bank", "Release request awaiting independent approval."),
            ("DEMO-FDR-005", institutions[4], 1500000, FdrStatus.closed, -120, "Union Bank of India", "Completed refund and closure scenario."),
            ("DEMO-FDR-006", institutions[5], 1500000, FdrStatus.draft, 180, "HDFC Bank", "Draft registration scenario for data entry."),
        ]
        fdrs: list[Fdr] = []
        for index, (identifier, institution, amount, status, days, bank, notes) in enumerate(scenarios):
            issue = now - timedelta(days=120)
            maturity = now + timedelta(days=days)
            fdr = Fdr(
                identifier=identifier,
                institution_id=institution.id,
                holder_name=institution.name,
                amount=amount,
                approval_case_reference=f"DEMO-CASE-{index + 1:03d}",
                bank_name=bank,
                branch_name="Main Branch",
                ifsc_code=f"DEMO0{index + 1:06d}"[:11],
                amount_in_words=f"Rupees {amount:,} only",
                issue_date=issue,
                beneficiary="AICTE / Designated Authority",
                joint_holder=institution.name,
                lien_endorsed=True,
                lien_clause="Irrevocable lien marked in favour of the designated beneficiary.",
                maturity_date=maturity,
                status=status,
                created_by=user.id,
            )
            db.add(fdr)
            db.flush()
            fdrs.append(fdr)
            db.add(InstrumentVersion(fdr_id=fdr.id, version_number=1, change_reason="Demo scenario seed", snapshot=identifier, created_by=user.id))
            db.add(LifecycleEvent(fdr_id=fdr.id, from_status="", to_status=status.value, reason=notes, actor_id=user.id))
            db.add(FieldProvenance(fdr_id=fdr.id, field_name="amount", value=str(amount), level=ProvenanceLevel.declared, evidence_reference="Demo declaration"))
            db.add(AuditEvent(actor_id=user.id, action="scenario_seeded", entity="fdr", entity_id=str(fdr.id), details=notes))
            created += 1

        db.flush()
        db.add(VerificationCase(fdr_id=fdrs[0].id, status=VerificationStatus.verified, assigned_to=user.id, outcome_notes="Branch letter reviewed and instrument details reconciled.", evidence_reference="DEMO-BANK-001"))
        db.add(VerificationCase(fdr_id=fdrs[1].id, status=VerificationStatus.in_review, assigned_to=user.id, outcome_notes="Bank confirmation requested.", evidence_reference="DEMO-BANK-002"))
        db.add(VerificationCase(fdr_id=fdrs[2].id, status=VerificationStatus.pending, outcome_notes="Awaiting review.", evidence_reference=""))
        db.add(VerificationCase(fdr_id=fdrs[3].id, status=VerificationStatus.verified, assigned_to=user.id, outcome_notes="Verified before release request.", evidence_reference="DEMO-BANK-004"))

        db.add(Discrepancy(fdr_id=fdrs[1].id, rule_id="D06", severity="medium", explanation="OCR candidate amount differs from declared amount; officer review required.", expected_value="₹15,00,000", observed_value="₹14,50,000", status=DiscrepancyStatus.open))
        db.add(Discrepancy(fdr_id=fdrs[2].id, rule_id="D12", severity="high", explanation="Irrevocable lien clause is not visible in submitted evidence.", expected_value="Lien clause present", observed_value="Not found", status=DiscrepancyStatus.open))
        db.add(Discrepancy(fdr_id=fdrs[0].id, rule_id="D01", severity="low", explanation="Additional branch dispatch evidence was requested and received.", expected_value="Dispatch reference", observed_value="DEMO-DISPATCH-001", status=DiscrepancyStatus.resolved, resolution_notes="Dispatch evidence attached and reviewed.", resolved_by=user.id))

        db.add(ReleaseRequest(fdr_id=fdrs[3].id, request_type=ReleaseType.release, reason="Institution has completed the approved programme and submitted clearance evidence.", status="pending", requested_by=user.id))
        db.add(ReleaseRequest(fdr_id=fdrs[4].id, request_type=ReleaseType.refund, reason="Closed scenario: refund processed after completion of the controlled checklist.", status="executed", requested_by=user.id, approved_by=user.id, decision_notes="Demo completion record."))

        for fdr, event_type, location, custodian in (
            (fdrs[0], "received", "Vault A / Locker 12", "Custody Officer"),
            (fdrs[1], "received", "Vault A / Locker 13", "Custody Officer"),
            (fdrs[3], "transferred", "Review Desk / Cabinet 4", "Review Officer"),
        ):
            db.add(CustodyEvent(fdr_id=fdr.id, event_type=event_type, location=location, custodian=custodian, evidence_reference="DEMO-CUSTODY", remarks="Demo custody chain.", actor_id=user.id))

        db.add(NotificationEvent(fdr_id=fdrs[0].id, channel="in_app", reminder_days=30, recipient="admin", status="planned"))
        db.add(NotificationEvent(fdr_id=fdrs[3].id, channel="email", reminder_days=7, recipient="institution@example.test", status="planned"))

        if policies:
            db.add(DepositAssessment(institution_id=institutions[0].id, policy_rule_id=policies[0].id, amount=3500000, status="configured", notes="Demo assessment using AICTE handbook policy.", created_by=user.id))

        db.commit()
        return created


def seed_maturity_calendar() -> int:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.id))
        institutions = db.scalars(select(Institution).order_by(Institution.id).limit(6)).all()
        if not user or len(institutions) < 3:
            raise RuntimeError("The administrator and institution catalogue must be loaded first")

        existing_rows = db.scalars(select(Fdr).where(Fdr.identifier.like("DEMO-MATURITY-%"))).all()
        existing = {row.identifier for row in existing_rows}
        repaired = 0
        for row in existing_rows:
            if row.issue_date is None:
                maturity_date = row.maturity_date
                if maturity_date.tzinfo is None:
                    maturity_date = maturity_date.replace(tzinfo=timezone.utc)
                row.issue_date = maturity_date - timedelta(days=365)
                repaired += 1
        statuses = [FdrStatus.draft, FdrStatus.submitted, FdrStatus.under_review]
        created = 0
        following_month = 1 if now.month == 12 else now.month + 1
        following_year = now.year + 1 if now.month == 12 else now.year
        last_day = (datetime(following_year, following_month, 1, tzinfo=timezone.utc) - timedelta(days=1)).day
        current_month_day = min(now.day + 1, last_day)
        for position, hour in enumerate((12, 14, 16)):
            identifier = f"DEMO-MATURITY-CURRENT-{position + 1:02d}"
            if identifier in existing:
                continue
            institution = institutions[position % len(institutions)]
            maturity_date = datetime(now.year, now.month, current_month_day, hour, tzinfo=timezone.utc)
            fdr = Fdr(
                identifier=identifier,
                institution_id=institution.id,
                holder_name=institution.name,
                amount=750000 + position * 250000,
                issue_date=maturity_date - timedelta(days=365),
                maturity_date=maturity_date,
                status=statuses[position % len(statuses)],
                created_by=user.id,
            )
            db.add(fdr)
            db.flush()
            db.add(AuditEvent(
                actor_id=user.id,
                action="maturity_demo_seeded",
                entity="fdr",
                entity_id=str(fdr.id),
                details="Clearly labeled demo calendar data; not a verified instrument.",
            ))
            existing.add(identifier)
            created += 1

        for month_offset in range(12):
            year, month = divmod(now.month - 1 + month_offset, 12)
            year += now.year
            month += 1
            if month_offset == 0:
                maturity_dates = [now + timedelta(days=offset) for offset in (3, 6, 9)]
            else:
                maturity_dates = [datetime(year, month, day, 12, tzinfo=timezone.utc) for day in (5, 15, 25)]

            for position, maturity_date in enumerate(maturity_dates):
                identifier = f"DEMO-MATURITY-{month_offset + 1:02d}-{position + 1:02d}"
                if identifier in existing:
                    continue
                institution = institutions[(month_offset * 3 + position) % len(institutions)]
                fdr = Fdr(
                    identifier=identifier,
                    institution_id=institution.id,
                    holder_name=institution.name,
                    amount=500000 + ((month_offset * 3 + position) % 8) * 250000,
                    issue_date=maturity_date - timedelta(days=365),
                    maturity_date=maturity_date,
                    status=statuses[(month_offset + position) % len(statuses)],
                    created_by=user.id,
                )
                db.add(fdr)
                db.flush()
                db.add(AuditEvent(
                    actor_id=user.id,
                    action="maturity_demo_seeded",
                    entity="fdr",
                    entity_id=str(fdr.id),
                    details="Clearly labeled demo calendar data; not a verified instrument.",
                ))
                existing.add(identifier)
                created += 1

        db.commit()
        if repaired:
            print(f"Repaired {repaired} demo maturity issue dates")
        return created


def seed_demo_documents() -> int:
    source_dir = Path(__file__).parents[2] / "project-main" / "data" / "documents"
    sources = sorted(source_dir.glob("*.pdf")) if source_dir.exists() else []
    handbook = Path.home() / "Downloads" / "AICTE-issued-the-Approval-Process-Handbook-feb202026.pdf"
    if not sources and handbook.exists():
        sources = [handbook]
    if not sources:
        return 0
    with SessionLocal() as db:
        fdrs = db.scalars(select(Fdr).where(Fdr.identifier.like("DEMO-FDR-%")).order_by(Fdr.id).limit(len(sources))).all()
        created = 0
        upload_root = Path(settings.upload_dir)
        upload_root.mkdir(parents=True, exist_ok=True)
        for fdr, source in zip(fdrs, sources):
            content = source.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if db.scalar(select(Document).where(Document.sha256 == digest)):
                continue
            stored = f"demo-{digest[:20]}.pdf"
            shutil.copyfile(source, upload_root / stored)
            db.add(Document(
                fdr_id=fdr.id,
                original_name=f"Demo evidence - {source.name}",
                stored_name=stored,
                sha256=digest,
                content_type="application/pdf",
                size=len(content),
            ))
            db.add(AuditEvent(actor_id=fdr.created_by, action="scenario_document_seeded", entity="document", entity_id=stored, details="Demo evidence only"))
            created += 1
        db.commit()
        return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed linked VaultTrace demo scenarios")
    parser.add_argument("--maturity-calendar-only", action="store_true", help="Seed only clearly labeled maturity calendar examples")
    args = parser.parse_args()
    if args.maturity_calendar_only:
        print(f"Created {seed_maturity_calendar()} demo maturity calendar records")
        return
    print(f"Created {seed_scenarios()} demo FDR scenarios")
    print(f"Created {seed_demo_documents()} demo evidence documents")


if __name__ == "__main__":
    main()
