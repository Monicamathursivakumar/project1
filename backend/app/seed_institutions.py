"""Import the AICTE institution catalogue into the application database.

Usage:
    python -m app.seed_institutions ..\all-institutions-with-programmes.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import inspect, select, text

from .main import Base, Institution, InstitutionProgramme, SessionLocal, engine


def ensure_dataset_schema() -> None:
    inspector = inspect(engine)
    institution_columns = {column["name"] for column in inspector.get_columns("institutions")}
    additions = {
        "aicte_id": "VARCHAR(100)",
        "other_id": "VARCHAR(100)",
        "district": "VARCHAR(150) NOT NULL DEFAULT ''",
        "state": "VARCHAR(150) NOT NULL DEFAULT ''",
        "institution_type": "VARCHAR(100) NOT NULL DEFAULT ''",
        "women": "VARCHAR(10) NOT NULL DEFAULT ''",
        "minority": "VARCHAR(10) NOT NULL DEFAULT ''",
        "university": "VARCHAR(500) NOT NULL DEFAULT ''",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in institution_columns:
                connection.execute(text(f"ALTER TABLE institutions ADD COLUMN {name} {definition}"))
    Base.metadata.create_all(engine)


def import_dataset(path: Path, batch_size: int = 500) -> tuple[int, int]:
    ensure_dataset_schema()
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Dataset root must be a JSON array")

    imported_institutions = 0
    imported_programmes = 0
    with SessionLocal() as db:
        existing_codes = set(db.scalars(select(Institution.code)).all())
        pending_institutions: list[Institution] = []
        pending_programmes: list[dict] = []

        for index, record in enumerate(records, start=1):
            aicte_id = str(record.get("aicte_id") or "").strip()
            code = aicte_id or str(record.get("other_id") or "").strip()
            name = str(record.get("institute_name") or "").strip()
            if not name or not code:
                raise ValueError(f"Record {index} is missing institute_name or an identifier")
            if code in existing_codes:
                continue

            institution = Institution(
                name=name,
                code=code,
                address=str(record.get("address") or "").strip(),
                aicte_id=aicte_id or None,
                other_id=str(record.get("other_id") or "").strip() or None,
                district=str(record.get("district") or "").strip(),
                state=str(record.get("state") or "").strip(),
                institution_type=str(record.get("institution_type") or "").strip(),
                women=str(record.get("women") or "").strip(),
                minority=str(record.get("minority") or "").strip(),
                university=str(record.get("university") or "").strip(),
            )
            db.add(institution)
            db.flush()
            imported_institutions += 1
            existing_codes.add(code)

            for programme in record.get("programmes") or []:
                db.add(InstitutionProgramme(
                    institution_id=institution.id,
                    programme=str(programme.get("programme") or "").strip(),
                    level=str(programme.get("level") or "").strip(),
                    course=str(programme.get("course") or "").strip(),
                    course_type=str(programme.get("course_type") or "").strip(),
                    shift=str(programme.get("shift") or "").strip(),
                    availability=str(programme.get("availability") or "").strip(),
                    intake=str(programme.get("intake") or "").strip(),
                    enrollment=str(programme.get("enrollment") or "").strip(),
                    placement=str(programme.get("placement") or "").strip(),
                ))
                imported_programmes += 1

            if imported_institutions % batch_size == 0:
                db.commit()

        db.commit()
    return imported_institutions, imported_programmes


def main() -> None:
    parser = argparse.ArgumentParser(description="Import AICTE institutions and programmes")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    imported_institutions, imported_programmes = import_dataset(args.dataset)
    print(f"Imported {imported_institutions} institutions and {imported_programmes} programmes")


if __name__ == "__main__":
    main()
