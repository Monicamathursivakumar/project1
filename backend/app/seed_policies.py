"""Load security-deposit rules from AICTE Approval Process Handbook Table 1.4.

The values are stored in INR because DepositAssessment.amount is stored in INR,
while the handbook table expresses them in lakh.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from .main import AuditEvent, PolicyRule, Role, SessionLocal, User


SOURCE = "AICTE Approval Process Handbook 2024-2027, Clause 1.12, Table 1.4, printed page 10 (PDF page 26)"
EFFECTIVE = datetime(2024, 4, 1, tzinfo=timezone.utc)
EXPIRY = datetime(2027, 3, 31, 23, 59, 59, tzinfo=timezone.utc)

RULES = [
    ("ENGINEERING_TECHNOLOGY", "Engineering and Technology", {"diploma": 15, "undergraduate": 35, "postgraduate": 15}),
    ("PLANNING", "Planning", {"diploma": 15, "undergraduate": 15, "postgraduate": 15}),
    ("APPLIED_ARTS_CRAFTS", "Applied Arts and Crafts", {"diploma": 15, "undergraduate": 15, "postgraduate": 15}),
    ("DESIGN", "Design", {"diploma": 15, "undergraduate": 15, "postgraduate": 15}),
    ("HMCT", "Hotel Management and Catering Technology (HMCT)", {"diploma": 15, "undergraduate": 15, "postgraduate": 15}),
    ("COMPUTER_APPLICATIONS", "Computer Applications (BCA, MCA, etc.)", {"undergraduate": 5, "postgraduate": 15}),
    ("MANAGEMENT", "Management (BBA, MBA, etc.)", {"undergraduate": 5, "postgraduate": 15}),
]

LEVEL_LABELS = {
    "diploma": "Diploma / Post Diploma",
    "undergraduate": "Under Graduate",
    "postgraduate": "Post Graduate Diploma / Post Graduate Degree",
}


def seed_policies() -> int:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role == Role.admin).order_by(User.id))
        if not user:
            raise RuntimeError("An administrator must exist before loading policy rules")

        created = 0
        for category, label, levels in RULES:
            for level, lakh in levels.items():
                rule_id = f"APH-1.12-{category}-{level.upper()}"
                if db.scalar(select(PolicyRule).where(PolicyRule.rule_id == rule_id)):
                    continue
                description = (
                    f"Security Deposit for {label}, {LEVEL_LABELS[level]}. "
                    f"Table value: INR {lakh} lakh. The principal remains with the Council for 10 years. "
                    "The amount is double in case of private leased building / land."
                )
                db.add(PolicyRule(
                    rule_id=rule_id,
                    description=description,
                    required_documents=json.dumps(["Security Deposit FDR", "Affidavit 3"]),
                    amount_floor=lakh * 100_000,
                    effective_date=EFFECTIVE,
                    expiry_date=EXPIRY,
                    version=1,
                    active=True,
                    source_reference=SOURCE,
                    created_by=user.id,
                ))
                db.add(AuditEvent(
                    actor_id=user.id,
                    action="policy_seeded",
                    entity="policy",
                    entity_id=rule_id,
                    details=SOURCE,
                ))
                created += 1
        db.commit()
        return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Load AICTE Table 1.4 security deposit policies")
    parser.parse_args()
    print(f"Created {seed_policies()} AICTE policy rules")


if __name__ == "__main__":
    main()
