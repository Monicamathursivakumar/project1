from fastapi.testclient import TestClient
from app.main import app, Document, ExtractionResult, Fdr, Institution, ReleaseRequest, Role, SessionLocal, User, UserInstitutionMembership, pwd_context, select
from datetime import datetime, timezone
import io
import uuid
import fitz
from unittest.mock import patch
client = TestClient(app)
def test_health(): assert client.get("/health").json()["status"] == "ok"
def test_bootstrap_and_auth():
    bootstrap = client.post("/api/auth/bootstrap")
    assert bootstrap.status_code in (200, 409)
    response = client.post("/api/auth/token", data={"username": "admin", "password": "ChangeMe123!"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def auth_headers():
    response = client.post("/api/auth/token", data={"username": "admin", "password": "ChangeMe123!"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_institution_csv_preview_and_import():
    headers = auth_headers()
    code = f"CSV-{uuid.uuid4().hex[:8]}"
    csv_file = {"file": ("institutions.csv", io.BytesIO(f"name,code,address\nDemo Academy,{code},Delhi\n".encode()), "text/csv")}
    preview = client.post("/api/institutions/import/preview", headers=headers, files=csv_file)
    assert preview.status_code == 200
    assert preview.json()["errors"] == []
    imported = client.post(f"/api/institutions/import/{preview.json()['job_id']}", headers=headers)
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1


def test_institution_pagination_and_identifier_search():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    first = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Directory Academy {suffix}", "code": f"DIR-{suffix}"},
    )
    second = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Directory College {suffix}", "code": f"COL-{suffix}"},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    page = client.get("/api/institutions", headers=headers, params={"q": suffix, "page": 1, "page_size": 1})
    assert page.status_code == 200
    assert len(page.json()) == 1

    identifier = client.get("/api/institutions", headers=headers, params={"q": f"DIR-{suffix}"})
    assert identifier.status_code == 200
    assert [item["code"] for item in identifier.json()] == [f"DIR-{suffix}"]

    invalid = client.get("/api/institutions", headers=headers, params={"page_size": 101})
    assert invalid.status_code == 422


def test_institution_membership_limits_scoped_user_access():
    admin_headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    first = client.post(
        "/api/institutions",
        headers=admin_headers,
        json={"name": f"Scoped Academy {suffix}", "code": f"SCOPE-A-{suffix}"},
    )
    second = client.post(
        "/api/institutions",
        headers=admin_headers,
        json={"name": f"Restricted College {suffix}", "code": f"SCOPE-B-{suffix}"},
    )
    assert first.status_code == 200
    assert second.status_code == 200

    username = f"officer-{suffix}"
    with SessionLocal() as db:
        scoped_user = User(username=username, password_hash=pwd_context.hash("ScopedPass123!"), role=Role.officer)
        db.add(scoped_user)
        db.commit()
        db.refresh(scoped_user)
        user_id = scoped_user.id

    membership = client.post(
        "/api/institution-memberships",
        headers=admin_headers,
        json={"user_id": user_id, "institution_id": first.json()["id"]},
    )
    assert membership.status_code == 200

    token = client.post("/api/auth/token", data={"username": username, "password": "ScopedPass123!"})
    assert token.status_code == 200
    scoped_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    visible = client.get("/api/institutions", headers=scoped_headers, params={"q": suffix})
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()] == [first.json()["id"]]

    denied = client.get(f"/api/institutions/{second.json()['id']}/programmes", headers=scoped_headers)
    assert denied.status_code == 403


def test_policy_activation_requires_current_effective_period():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    future = client.post(
        "/api/policies",
        headers=headers,
        json={
            "rule_id": f"FUTURE-{suffix}",
            "description": "A future policy rule for activation testing",
            "amount_floor": 100,
            "effective_date": "2099-01-01T00:00:00Z",
            "active": False,
            "required_documents": [],
        },
    )
    assert future.status_code == 200
    activation = client.patch(
        f"/api/policies/{future.json()['id']}/status",
        headers=headers,
        json={"active": True},
    )
    assert activation.status_code == 422

    current = client.post(
        "/api/policies",
        headers=headers,
        json={
            "rule_id": f"CURRENT-{suffix}",
            "description": "A current policy rule for activation testing",
            "amount_floor": 100,
            "effective_date": "2020-01-01T00:00:00Z",
            "active": False,
            "required_documents": [],
        },
    )
    assert current.status_code == 200
    activated = client.patch(
        f"/api/policies/{current.json()['id']}/status",
        headers=headers,
        json={"active": True},
    )
    assert activated.status_code == 200
    assert activated.json()["active"] is True
    deactivated = client.patch(
        f"/api/policies/{current.json()['id']}/status",
        headers=headers,
        json={"active": False},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False


def test_renewal_request_creates_linked_version_and_reopens_scrutiny():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Renewal Academy {suffix}", "code": f"RENEW-{suffix}"},
    )
    assert institution.status_code == 200
    payload = {
        "identifier": f"FDR-RENEW-{suffix}",
        "institution_id": institution.json()["id"],
        "holder_name": "Renewal Institution",
        "approval_case_reference": f"CASE-RENEW-{suffix}",
        "bank_name": "Example Scheduled Bank",
        "branch_name": "Main Branch",
        "ifsc_code": "SBIN0001234",
        "amount": 250000,
        "amount_in_words": "Rupees Two Lakh Fifty Thousand Only",
        "issue_date": "2026-01-15T00:00:00Z",
        "maturity_date": "2027-01-15T00:00:00Z",
        "beneficiary": "VaultTrace Authority",
        "joint_holder": "Renewal Institution",
        "lien_endorsed": True,
        "lien_clause": "Lien recorded in favour of beneficiary.",
    }
    created = client.post("/api/fdrs", headers=headers, json=payload)
    assert created.status_code == 200
    fdr_id = created.json()["id"]
    verified = client.patch(f"/api/fdrs/{fdr_id}/status", headers=headers, json={"status": "submitted"})
    assert verified.status_code == 200
    under_review = client.patch(f"/api/fdrs/{fdr_id}/status", headers=headers, json={"status": "under_review"})
    assert under_review.status_code == 200
    reviewer = client.post("/api/auth/token", data={"username": "admin", "password": "ChangeMe123!"})
    assert reviewer.status_code == 200
    verified = client.post(
        f"/api/fdrs/{fdr_id}/verification",
        headers=headers,
        json={"status": "verified", "outcome_notes": "Evidence reviewed and accepted.", "evidence_reference": "document-renew-001"},
    )
    assert verified.status_code == 200

    renewal = client.post(
        f"/api/fdrs/{fdr_id}/renewal-replacement",
        headers=headers,
        json={
            "change_type": "renewal",
            "reason": "Renewal requested before the current instrument matures.",
            "proposed_identifier": f"FDR-RENEWED-{suffix}",
            "proposed_maturity_date": "2028-01-15T00:00:00Z",
        },
    )
    assert renewal.status_code == 200
    assert renewal.json()["version_number"] == 2
    assert renewal.json()["status"] == "draft"

    versions = client.get(f"/api/fdrs/{fdr_id}/versions", headers=headers)
    assert versions.status_code == 200
    assert len(versions.json()) == 2
    assert "FDR-RENEWED" in versions.json()[-1]["snapshot"]


def test_release_closure_cannot_be_performed_by_executor():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        reviewer = User(username=f"release-reviewer-{suffix}", password_hash=pwd_context.hash("ReviewerPass123!"), role=Role.reviewer)
        db.add(reviewer)
        db.flush()
        institution = Institution(name=f"Release Academy {suffix}", code=f"REL-{suffix}")
        db.add(institution)
        db.commit()
        db.refresh(institution)
        fdr = Fdr(
            identifier=f"FDR-REL-{suffix}",
            institution_id=institution.id,
            holder_name="Release Institution",
            amount=100000,
            approval_case_reference=f"CASE-REL-{suffix}",
            bank_name="Example Bank",
            branch_name="Main Branch",
            ifsc_code="SBIN0001234",
            amount_in_words="Rupees One Lakh Only",
            issue_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
            beneficiary="VaultTrace Authority",
            joint_holder="Release Institution",
            lien_endorsed=False,
            status="verified",
            created_by=reviewer.id,
        )
        db.add(fdr)
        db.commit()
        db.refresh(fdr)
        request = ReleaseRequest(fdr_id=fdr.id, request_type="release", reason="Release after verified closure review.", requested_by=reviewer.id, status="approved", approved_by=reviewer.id)
        db.add(request)
        db.commit()
        db.refresh(request)
        request_id = request.id

    executed = client.post(
        f"/api/release-requests/{request_id}/execute",
        headers=headers,
        json={"evidence_reference": "bank-confirmation-REL", "execution_notes": "Transfer evidence recorded."},
    )
    assert executed.status_code == 200
    closed = client.post(
        f"/api/release-requests/{request_id}/close",
        headers=headers,
        json={"evidence_reference": "closure-confirmation-REL", "execution_notes": "Closure evidence recorded."},
    )
    assert closed.status_code == 403


def test_notification_delivery_boundary_marks_external_channel_unavailable():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Notification Academy {suffix}", "code": f"NOTIFY-{suffix}"},
    )
    assert institution.status_code == 200
    fdr = client.post(
        "/api/fdrs",
        headers=headers,
        json={
            "identifier": f"FDR-NOTIFY-{suffix}",
            "institution_id": institution.json()["id"],
            "holder_name": "Notification Institution",
            "approval_case_reference": f"CASE-NOTIFY-{suffix}",
            "bank_name": "Example Bank",
            "branch_name": "Main Branch",
            "ifsc_code": "SBIN0001234",
            "amount": 100000,
            "amount_in_words": "Rupees One Lakh Only",
            "issue_date": "2026-01-01T00:00:00Z",
            "maturity_date": "2027-01-01T00:00:00Z",
            "beneficiary": "VaultTrace Authority",
            "joint_holder": "Notification Institution",
            "lien_endorsed": False,
        },
    )
    assert fdr.status_code == 200
    notification = client.post(
        f"/api/fdrs/{fdr.json()['id']}/notifications",
        headers=headers,
        json={"channel": "email", "reminder_days": 30, "recipient": f"ops-{suffix}@example.test"},
    )
    assert notification.status_code == 200
    notification_id = notification.json()["id"]
    assert notification.json()["status"] == "planned"

    unavailable = client.patch(
        f"/api/notifications/{notification_id}/status",
        headers=headers,
        json={"status": "unavailable", "reason": "No email provider is configured in this environment."},
    )
    assert unavailable.status_code == 200
    assert unavailable.json()["status"] == "unavailable"

    repeated = client.patch(
        f"/api/notifications/{notification_id}/status",
        headers=headers,
        json={"status": "unavailable", "reason": "Repeated transition should be rejected."},
    )
    assert repeated.status_code == 422


def test_instrument_export_is_scoped_and_audited():
    admin_headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        officer = User(username=f"export-officer-{suffix}", password_hash=pwd_context.hash("ExportPass123!"), role=Role.officer)
        first = Institution(name=f"Export Academy {suffix}", code=f"EXPORT-A-{suffix}")
        second = Institution(name=f"Hidden Export College {suffix}", code=f"EXPORT-B-{suffix}")
        db.add_all([officer, first, second])
        db.flush()
        db.add(UserInstitutionMembership(user_id=officer.id, institution_id=first.id))
        db.add_all([
            Fdr(
                identifier=f"FDR-EXPORT-A-{suffix}", institution_id=first.id, holder_name="Export Academy",
                amount=100000, approval_case_reference=f"CASE-A-{suffix}", bank_name="Example Bank",
                branch_name="Main Branch", ifsc_code="SBIN0001234", amount_in_words="Rupees One Lakh Only",
                issue_date=datetime(2026, 1, 1, tzinfo=timezone.utc), maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
                beneficiary="Authority", joint_holder="Export Academy", created_by=officer.id,
            ),
            Fdr(
                identifier=f"FDR-EXPORT-B-{suffix}", institution_id=second.id, holder_name="Hidden College",
                amount=200000, approval_case_reference=f"CASE-B-{suffix}", bank_name="Example Bank",
                branch_name="Main Branch", ifsc_code="SBIN0001234", amount_in_words="Rupees Two Lakh Only",
                issue_date=datetime(2026, 1, 1, tzinfo=timezone.utc), maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
                beneficiary="Authority", joint_holder="Hidden College", created_by=officer.id,
            ),
        ])
        db.commit()
        officer_id = officer.id

    token = client.post("/api/auth/token", data={"username": f"export-officer-{suffix}", "password": "ExportPass123!"})
    assert token.status_code == 200
    officer_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    exported = client.get("/api/reports/instruments.csv", headers=officer_headers)
    assert exported.status_code == 200
    assert f"FDR-EXPORT-A-{suffix}" in exported.text
    assert f"FDR-EXPORT-B-{suffix}" not in exported.text

    audit = client.get("/api/audit", headers=admin_headers, params={"action": "instrument_exported"})
    assert audit.status_code == 200
    assert any(event["actor_id"] == officer_id and event["entity_id"] == "instruments.csv" for event in audit.json())


def test_aggregate_views_are_scoped_to_membership():
    admin_headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        officer = User(username=f"aggregate-officer-{suffix}", password_hash=pwd_context.hash("AggregatePass123!"), role=Role.officer)
        assigned = Institution(name=f"Aggregate Academy {suffix}", code=f"AGG-A-{suffix}")
        hidden = Institution(name=f"Aggregate Hidden {suffix}", code=f"AGG-B-{suffix}")
        db.add_all([officer, assigned, hidden])
        db.flush()
        db.add(UserInstitutionMembership(user_id=officer.id, institution_id=assigned.id))
        db.add_all([
            Fdr(identifier=f"FDR-AGG-A-{suffix}", institution_id=assigned.id, holder_name="Assigned", amount=100,
                approval_case_reference=f"CASE-A-{suffix}", bank_name="Bank", branch_name="Branch", ifsc_code="SBIN0001234",
                amount_in_words="One Hundred", issue_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc), beneficiary="Authority",
                joint_holder="Assigned", created_by=officer.id),
            Fdr(identifier=f"FDR-AGG-B-{suffix}", institution_id=hidden.id, holder_name="Hidden", amount=200,
                approval_case_reference=f"CASE-B-{suffix}", bank_name="Bank", branch_name="Branch", ifsc_code="SBIN0001234",
                amount_in_words="Two Hundred", issue_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
                maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc), beneficiary="Authority",
                joint_holder="Hidden", created_by=officer.id),
        ])
        db.commit()

    token = client.post("/api/auth/token", data={"username": f"aggregate-officer-{suffix}", "password": "AggregatePass123!"})
    assert token.status_code == 200
    scoped_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    summary = client.get("/api/dashboard/summary", headers=scoped_headers)
    assert summary.status_code == 200
    assert summary.json()["institutions"] == 1
    assert summary.json()["fdrs"] == 1
    directory = client.get("/api/institutions/summary", headers=scoped_headers)
    assert directory.status_code == 200
    assert directory.json()["institutions"] == 1


def test_terminal_verification_requires_evidence_reference():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Verification Academy {suffix}", "code": f"VERIFY-{suffix}"},
    )
    assert institution.status_code == 200
    fdr = client.post(
        "/api/fdrs",
        headers=headers,
        json={
            "identifier": f"FDR-VERIFY-{suffix}",
            "institution_id": institution.json()["id"],
            "holder_name": "Verification Institution",
            "approval_case_reference": f"CASE-VERIFY-{suffix}",
            "bank_name": "Example Bank",
            "branch_name": "Main Branch",
            "ifsc_code": "SBIN0001234",
            "amount": 100000,
            "amount_in_words": "Rupees One Lakh Only",
            "issue_date": "2026-01-01T00:00:00Z",
            "maturity_date": "2027-01-01T00:00:00Z",
            "beneficiary": "VaultTrace Authority",
            "joint_holder": "Verification Institution",
            "lien_endorsed": False,
        },
    )
    assert fdr.status_code == 200
    fdr_id = fdr.json()["id"]
    submitted = client.patch(f"/api/fdrs/{fdr_id}/status", headers=headers, json={"status": "submitted"})
    assert submitted.status_code == 200
    under_review = client.patch(f"/api/fdrs/{fdr_id}/status", headers=headers, json={"status": "under_review"})
    assert under_review.status_code == 200
    missing = client.post(
        f"/api/fdrs/{fdr_id}/verification",
        headers=headers,
        json={"status": "verified", "outcome_notes": "Evidence reviewed."},
    )
    assert missing.status_code == 422
    valid = client.post(
        f"/api/fdrs/{fdr_id}/verification",
        headers=headers,
        json={"status": "verified", "outcome_notes": "Evidence reviewed.", "evidence_reference": "document-verify-001"},
    )
    assert valid.status_code == 200
    assert valid.json()["fdr_status"] == "verified"


def test_pdf_extraction_persists_text_without_claiming_authenticity():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post("/api/institutions", headers=headers, json={"name": f"PDF Academy {suffix}", "code": f"PDF-{suffix}"})
    assert institution.status_code == 200
    fdr = client.post("/api/fdrs", headers=headers, json={
        "identifier": f"FDR-PDF-{suffix}", "institution_id": institution.json()["id"], "holder_name": "PDF Institution",
        "approval_case_reference": f"CASE-PDF-{suffix}", "bank_name": "Example Bank", "branch_name": "Main Branch",
        "ifsc_code": "SBIN0001234", "amount": 100000, "amount_in_words": "Rupees One Lakh Only",
        "issue_date": "2026-01-01T00:00:00Z", "maturity_date": "2027-01-01T00:00:00Z",
        "beneficiary": "VaultTrace Authority", "joint_holder": "PDF Institution", "lien_endorsed": False,
    })
    assert fdr.status_code == 200
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "FDR number: FDR-PDF evidence text")
    content = pdf.tobytes()
    pdf.close()
    uploaded = client.post(
        f"/api/fdrs/{fdr.json()['id']}/documents",
        headers=headers,
        files={"file": ("evidence.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert uploaded.status_code == 200
    extracted = client.post(f"/api/documents/{uploaded.json()['id']}/extract", headers=headers)
    assert extracted.status_code == 200
    assert extracted.json()["provider"] == "local-pymupdf"
    assert "FDR-PDF evidence text" in extracted.json()["text"]
    assert extracted.json()["authenticity_confirmed"] is False
    scanned = fitz.open()
    scanned.new_page()
    scanned_content = scanned.tobytes()
    scanned.close()
    scanned_upload = client.post(
        f"/api/fdrs/{fdr.json()['id']}/documents",
        headers=headers,
        files={"file": ("scanned.pdf", io.BytesIO(scanned_content), "application/pdf")},
    )
    assert scanned_upload.status_code == 200
    with patch("app.main.pytesseract.image_to_string", return_value="OCR FDR text"):
        scanned_extraction = client.post(
            f"/api/documents/{scanned_upload.json()['id']}/extract",
            headers=headers,
        )
    assert scanned_extraction.status_code == 200
    assert scanned_extraction.json()["provider"] == "local-tesseract"
    assert scanned_extraction.json()["text"] == "OCR FDR text"


def test_affidavit_conversion_returns_fields_from_extraction_not_source_fdr():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    source_institution = client.post(
        "/api/institutions", headers=headers,
        json={"name": f"Unrelated Source {suffix}", "code": f"SRC-{suffix}"},
    )
    extracted_institution = client.post(
        "/api/institutions", headers=headers,
        json={"name": "Sri Venkateswara Institute of Technology (DEMO)", "code": f"SVIT-{suffix}"},
    )
    assert source_institution.status_code == 200
    assert extracted_institution.status_code == 200
    source_fdr = client.post("/api/fdrs", headers=headers, json={
        "identifier": f"FDR-SOURCE-{suffix}", "institution_id": source_institution.json()["id"],
        "holder_name": "Unrelated source holder", "approval_case_reference": f"OLD-CASE-{suffix}",
        "bank_name": "Old Source Bank", "branch_name": "Old Source Branch", "ifsc_code": "SBIN0001234",
        "amount": 100000, "amount_in_words": "Rupees One Lakh Only",
        "issue_date": "2025-01-01T00:00:00Z", "maturity_date": "2026-01-01T00:00:00Z",
        "beneficiary": "Old Source Beneficiary", "joint_holder": "Old Source Holder", "lien_endorsed": False,
    })
    assert source_fdr.status_code == 200
    pdf = fitz.open()
    pdf.new_page()
    content = pdf.tobytes()
    pdf.close()
    uploaded = client.post(
        f"/api/fdrs/{source_fdr.json()['id']}/documents",
        headers=headers,
        files={"file": ("affidavit.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert uploaded.status_code == 200
    affidavit_text = """I/we, R. Karthik, Chairperson / Secretary, Sri Venkateswara Educational Trust.
1. I/we have applied for closure of our Institution Sri Venkateswara Institute of Technology (DEMO)
vide application DEMO-AICTE-2026-0142 dated 15/09/2026.
2. Our Trust Sri Venkateswara Educational Trust vide resolution Resolution No. SVET/2026/09.
Details of RPGF/ Joint FDR
Details of RPGF/ Joint FDR/RTGS made with AICTE/Board
Demo National
Bank 01/10/2026 ~25,00,000 DEMO-TRX-681204 01/10/2036
DEMO-FDR-2026-0081"""
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        db.add(ExtractionResult(
            document_id=uploaded.json()["id"], provider="test-ocr", status="completed",
            page_count=1, extracted_text=affidavit_text, authenticity_confirmed=False, created_by=admin.id,
        ))
        db.commit()
    with patch("app.main._openai_candidates", return_value={}):
        converted = client.post(
            f"/api/documents/{uploaded.json()['id']}/convert-to-fdr-draft",
            headers=headers,
            params={"fdr_id": source_fdr.json()["id"]},
        )
    assert converted.status_code == 200
    fields = converted.json()["fields"]
    assert fields["identifier"] == "DEMO-FDR-2026-0081"
    assert fields["institution_name"] == "Sri Venkateswara Institute of Technology (DEMO)"
    assert fields["institution_id"] != str(source_institution.json()["id"])
    with SessionLocal() as db:
        matched_institution = db.get(Institution, int(fields["institution_id"]))
        assert "sri venkateswara institute of technology" in matched_institution.name.lower()
    assert fields["approval_case_reference"] == "DEMO-AICTE-2026-0142"
    assert fields["bank_name"] == "Demo National Bank"
    assert fields["amount"] == "2500000"
    assert fields["issue_date"] == "2026-10-01"
    assert fields["maturity_date"] == "2036-10-01"
    assert fields["beneficiary"] == "AICTE/Board"
    assert fields["joint_holder"] == "Sri Venkateswara Institute of Technology (DEMO)"
    assert fields["branch_name"] is None
    assert fields["ifsc_code"] is None
    assert fields["amount_in_words"] is None


def test_policy_assessment_requires_configured_rule_or_marks_pending():
    headers = auth_headers()
    institution = client.post("/api/institutions", headers=headers, json={"name": "Assessment Academy", "code": "ASSESS-001"})
    assert institution.status_code in (200, 409)
    institution_id = institution.json().get("id") if institution.status_code == 200 else client.get("/api/institutions?q=Assessment", headers=headers).json()[0]["id"]
    assessment = client.post("/api/assessments", headers=headers, json={"institution_id": institution_id, "amount": 1000, "notes": "Awaiting authorised policy"})
    assert assessment.status_code == 200
    assert assessment.json()["status"] == "policy_required"


def test_detailed_fdr_registration_persists_declared_fields():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post("/api/institutions", headers=headers, json={"name": f"FDR Academy {suffix}", "code": f"FDR-{suffix}"})
    assert institution.status_code == 200
    payload = {
        "identifier": f"FDR-{suffix}",
        "institution_id": institution.json()["id"],
        "holder_name": "Authorised Institution",
        "approval_case_reference": f"CASE-{suffix}",
        "bank_name": "Example Scheduled Bank",
        "branch_name": "Main Branch",
        "ifsc_code": "SBIN0001234",
        "amount": 250000,
        "amount_in_words": "Rupees Two Lakh Fifty Thousand Only",
        "issue_date": "2026-01-15T00:00:00Z",
        "maturity_date": "2027-01-15T00:00:00Z",
        "beneficiary": "VaultTrace Authority",
        "joint_holder": "Authorised Institution",
        "lien_endorsed": True,
        "lien_clause": "Lien recorded in favour of beneficiary.",
    }
    response = client.post("/api/fdrs", headers=headers, json=payload)
    assert response.status_code == 200
    assert response.json()["approval_case_reference"] == payload["approval_case_reference"]
    assert response.json()["ifsc_code"] == payload["ifsc_code"]


def test_detailed_fdr_registration_rejects_invalid_dates_and_ifsc():
    headers = auth_headers()
    payload = {
        "identifier": f"FDR-{uuid.uuid4().hex[:8]}",
        "institution_id": 1,
        "holder_name": "Institution",
        "approval_case_reference": "CASE-INVALID",
        "bank_name": "Example Bank",
        "branch_name": "Main Branch",
        "ifsc_code": "not-an-ifsc",
        "amount": 100,
        "amount_in_words": "One Hundred Rupees",
        "issue_date": "2027-01-15T00:00:00Z",
        "maturity_date": "2026-01-15T00:00:00Z",
        "beneficiary": "Authority",
        "joint_holder": "Institution",
        "lien_endorsed": False,
    }
    response = client.post("/api/fdrs", headers=headers, json=payload)
    assert response.status_code == 422


def test_incomplete_extraction_can_be_submitted_as_intake_draft():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Intake Academy {suffix}", "code": f"INTAKE-{suffix}"},
    )
    assert institution.status_code == 200
    fdr = client.post("/api/fdrs", headers=headers, json={
        "identifier": f"FDR-INTAKE-SOURCE-{suffix}",
        "institution_id": institution.json()["id"],
        "holder_name": "Intake Source Holder",
        "approval_case_reference": f"CASE-INTAKE-{suffix}",
        "bank_name": "Source Bank",
        "branch_name": "Source Branch",
        "ifsc_code": "SBIN0001234",
        "amount": 100000,
        "amount_in_words": "Rupees One Lakh Only",
        "issue_date": "2026-01-01T00:00:00Z",
        "maturity_date": "2027-01-01T00:00:00Z",
        "beneficiary": "Source Beneficiary",
        "joint_holder": "Intake Source Holder",
        "lien_endorsed": False,
    })
    assert fdr.status_code == 200
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "FDR document awaiting review")
    content = pdf.tobytes()
    pdf.close()
    uploaded = client.post(
        f"/api/fdrs/{fdr.json()['id']}/documents",
        headers=headers,
        files={"file": ("intake.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert uploaded.status_code == 200
    extraction = client.post(
        f"/api/documents/{uploaded.json()['id']}/extract",
        headers=headers,
    )
    assert extraction.status_code == 200

    submitted = client.post(
        "/api/fdr-intakes",
        headers=headers,
        json={
            "source_document_id": uploaded.json()["id"],
            "fields": {"bank_name": "Extracted Bank", "identifier": ""},
        },
    )
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending_completion"
    assert submitted.json()["candidate_fields"]["bank_name"] == "Extracted Bank"
    assert submitted.json()["candidate_fields"]["identifier"] == ""

    listed = client.get("/api/fdr-intakes", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == submitted.json()["id"] for item in listed.json())
