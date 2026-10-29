from fastapi.testclient import TestClient
import app.main as main
import app.seed_public_demo as public_demo_seed
from app.main import app, AuthTokenRecord, Document, EmployeeVerification, ExtractionResult, Fdr, Institution, RegistrationAuditEvent, ReleaseRequest, Role, SessionLocal, User, UserInstitutionMembership, pwd_context, select, settings, token_digest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import io
import json
import re
import uuid
import fitz
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
client = TestClient(app)
def test_health(): assert client.get("/health").json()["status"] == "ok"
def test_bootstrap_and_auth():
    bootstrap = client.post("/api/auth/bootstrap")
    assert bootstrap.status_code in (200, 409)
    response = client.post("/api/auth/token", data={"username": "admin", "password": "ChangeMe123!"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def register_request(monkeypatch, account_type="viewer", **overrides):
    suffix = uuid.uuid4().hex[:10]
    sent_messages = []
    monkeypatch.setattr(main, "send_account_email", lambda recipient, subject, body: sent_messages.append(body) or True)
    payload = {
        "username": f"register-{suffix}",
        "full_name": "Registration Example",
        "email": f"register-{suffix}@example.test",
        "password": "VaultTraceTest!123",
        "password_confirmation": "VaultTraceTest!123",
        "account_type": account_type,
        "organization_name": "",
        "institution_id": None,
        "employee_id": None,
        "department": "",
        "designation": "",
        "consent": True,
    }
    if account_type not in {"institution_user", "viewer"}:
        payload.update({
            "organization_name": "VaultTrace Demo Organization",
            "employee_id": f"EMP-{suffix}",
            "department": "Operations",
            "designation": "Officer",
        })
    payload.update(overrides)
    response = client.post("/api/auth/register", json=payload)
    token = None
    if response.status_code == 201 and sent_messages:
        match = re.search(r"[?&]verifyEmail=([A-Za-z0-9_-]+)", sent_messages[-1])
        token = match.group(1) if match else None
    return response, token, payload


def verify_email(token):
    return client.post("/api/auth/email/verify", json={"token": token})


def decide_registration(headers, registration_db_id, action, reason="Reviewed registration evidence."):
    return client.post(
        f"/api/admin/registration-requests/{registration_db_id}/decision",
        headers=headers,
        json={"action": action, "reason": reason},
    )


def test_registration_email_identity_role_approval_and_audit(monkeypatch):
    registered, token, payload = register_request(monkeypatch)
    assert registered.status_code == 201
    assert token
    registration_id = registered.json()["registration_id"]

    before_approval = client.post(
        "/api/auth/token",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert before_approval.status_code == 401

    verified = verify_email(token)
    assert verified.status_code == 200
    assert verified.json()["status"] == "pending_identity_verification"
    assert verify_email(token).status_code == 400

    with SessionLocal() as db:
        request = db.scalar(select(main.RegistrationRequest).where(main.RegistrationRequest.public_id == registration_id))
        assert request is not None
        request_id = request.id
        reviewer = User(
            username=f"reviewer-{uuid.uuid4().hex[:8]}",
            password_hash=pwd_context.hash("ReviewerPassword123!"),
            role=Role.reviewer,
        )
        db.add(reviewer)
        db.commit()
        reviewer_name = reviewer.username

    reviewer_token = client.post("/api/auth/token", data={"username": reviewer_name, "password": "ReviewerPassword123!"})
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token.json()['access_token']}"}
    cannot_grant_role = decide_registration(reviewer_headers, request_id, "approve_role")
    assert cannot_grant_role.status_code == 403

    admin_headers = auth_headers()
    assert decide_registration(admin_headers, request_id, "verify_identity").status_code == 200
    approved = decide_registration(admin_headers, request_id, "approve_role")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    login = client.post(
        "/api/auth/token",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 200

    with SessionLocal() as db:
        events = db.scalars(select(RegistrationAuditEvent).where(RegistrationAuditEvent.registration_id == request_id)).all()
        actions = {event.action for event in events}
        assert {"registration_submitted", "email_verified", "verify_identity", "approve_role"} <= actions
        registration = db.get(main.RegistrationRequest, request_id)
        user_id = registration.user_id

    suspended = client.patch(
        f"/api/admin/users/{user_id}/activation",
        headers=admin_headers,
        json={"active": False, "reason": "Suspension workflow test."},
    )
    assert suspended.status_code == 200
    suspended_login = client.post(
        "/api/auth/token",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert suspended_login.status_code == 401


def test_registration_rejects_invalid_and_duplicate_accounts(monkeypatch):
    invalid, _, _ = register_request(
        monkeypatch,
        password_confirmation="DifferentVaultTracePassword123!",
    )
    assert invalid.status_code == 422

    registered, _, payload = register_request(monkeypatch)
    assert registered.status_code == 201
    duplicate_username, _, _ = register_request(
        monkeypatch,
        username=payload["username"],
    )
    assert duplicate_username.status_code == 409
    duplicate_email, _, _ = register_request(
        monkeypatch,
        email=payload["email"],
    )
    assert duplicate_email.status_code == 409


def test_rejected_registration_requires_reason_and_stays_inactive(monkeypatch):
    registered, _, payload = register_request(monkeypatch)
    assert registered.status_code == 201
    registration_id = registered.json()["registration_id"]
    with SessionLocal() as db:
        request = db.scalar(select(main.RegistrationRequest).where(
            main.RegistrationRequest.public_id == registration_id,
        ))
        request_id = request.id

    admin_headers = auth_headers()
    missing_reason = client.post(
        f"/api/admin/registration-requests/{request_id}/decision",
        headers=admin_headers,
        json={"action": "reject", "reason": ""},
    )
    assert missing_reason.status_code == 422
    rejected = decide_registration(admin_headers, request_id, "reject", "Unable to verify the submitted organization.")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    login = client.post(
        "/api/auth/token",
        data={"username": payload["username"], "password": payload["password"]},
    )
    assert login.status_code == 401


def test_registration_id_card_is_private_and_reviewer_access_is_audited(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(main, "send_account_email", lambda recipient, subject, body: True)
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        institution_name = f"Review Institution {suffix}"
        institution = Institution(name=institution_name, code=f"REVIEW-{suffix}")
        db.add(institution)
        db.commit()
        institution_id = institution.id
    payload = {
        "username": f"id-card-{suffix}",
        "full_name": "ID Card Applicant",
        "email": f"id-card-{suffix}@example.test",
        "password": "VaultTraceTest!123",
        "password_confirmation": "VaultTraceTest!123",
        "account_type": "viewer",
        "organization_name": "",
        "institution_id": institution_id,
        "employee_id": None,
        "department": "",
        "designation": "",
        "consent": True,
    }
    image = Image.new("RGB", (32, 20), color="navy")
    image_bytes = io.BytesIO()
    png_info = PngInfo()
    png_info.add_text("private-note", "should not be retained")
    image.save(image_bytes, format="PNG", pnginfo=png_info)
    response = client.post(
        "/api/auth/register-with-evidence",
        data={"registration_data": json.dumps(payload)},
        files={"identity_card": ("card.png", image_bytes.getvalue(), "image/png")},
    )
    assert response.status_code == 201

    with SessionLocal() as db:
        registration = db.scalar(select(main.RegistrationRequest).where(
            main.RegistrationRequest.public_id == response.json()["registration_id"]
        ))
        assert registration is not None
        registration_db_id = registration.id
        stored_path = tmp_path / registration.identity_document_stored_name
        assert stored_path.is_file()
        assert registration.identity_document_content_type == "image/png"
        assert registration.identity_document_size == stored_path.stat().st_size
        assert registration.identity_document_sha256 == main.hashlib.sha256(stored_path.read_bytes()).hexdigest()
        viewer = User(
            username=f"image-viewer-{suffix}",
            password_hash=pwd_context.hash("ViewerPassword123!"),
            role=Role.viewer,
        )
        viewer_name = viewer.username
        db.add(viewer)
        db.commit()

    assert client.get(
        f"/api/admin/registration-requests/{registration_db_id}/identity-document"
    ).status_code == 401
    viewer_login = client.post(
        "/api/auth/token",
        data={"username": viewer_name, "password": "ViewerPassword123!"},
    )
    assert viewer_login.status_code == 200
    assert client.get(
        f"/api/admin/registration-requests/{registration_db_id}/identity-document",
        headers={"Authorization": f"Bearer {viewer_login.json()['access_token']}"},
    ).status_code == 403
    reviewer_response = client.get(
        f"/api/admin/registration-requests/{registration_db_id}/identity-document",
        headers=auth_headers(),
    )
    assert reviewer_response.status_code == 200
    assert reviewer_response.headers["cache-control"] == "no-store"
    assert reviewer_response.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(reviewer_response.content)) as reviewed_image:
        assert reviewed_image.size == (32, 20)
        assert "private-note" not in reviewed_image.info
    queued = client.get("/api/admin/registration-requests", headers=auth_headers())
    reviewed = next(item for item in queued.json() if item["id"] == registration_db_id)
    assert reviewed["has_identity_document"] is True
    assert reviewed["registration_id"] == response.json()["registration_id"]
    assert reviewed["username"] == payload["username"]
    assert reviewed["full_name"] == payload["full_name"]
    assert reviewed["email"] == payload["email"]
    assert reviewed["account_type"] == payload["account_type"]
    assert reviewed["identity_document_content_type"] == "image/png"
    assert reviewed["identity_document_size"] > 0
    assert reviewed["email_verified_at"] is None
    assert reviewed["institution_name"] == institution_name
    with SessionLocal() as db:
        actions = set(db.scalars(select(RegistrationAuditEvent.action).where(
            RegistrationAuditEvent.registration_id == registration_db_id
        )).all())
        assert {"identity_document_uploaded", "identity_document_viewed"} <= actions


def test_registration_id_card_rejects_non_image_files(monkeypatch):
    monkeypatch.setattr(main, "send_account_email", lambda recipient, subject, body: True)
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "username": f"bad-card-{suffix}",
        "full_name": "Invalid Image Applicant",
        "email": f"bad-card-{suffix}@example.test",
        "password": "VaultTraceTest!123",
        "password_confirmation": "VaultTraceTest!123",
        "account_type": "viewer",
        "consent": True,
    }
    response = client.post(
        "/api/auth/register-with-evidence",
        data={"registration_data": json.dumps(payload)},
        files={"identity_card": ("card.png", b"not an image", "image/png")},
    )
    assert response.status_code == 400


def test_employee_id_is_unique_and_role_waits_for_employee_review(monkeypatch):
    registered, token, payload = register_request(monkeypatch, account_type="reviewing_officer")
    assert registered.status_code == 201
    assert token
    duplicate, _, _ = register_request(
        monkeypatch,
        account_type="reviewing_officer",
        employee_id=payload["employee_id"],
    )
    assert duplicate.status_code == 409
    assert verify_email(token).status_code == 200

    with SessionLocal() as db:
        request = db.scalar(select(main.RegistrationRequest).where(main.RegistrationRequest.public_id == registered.json()["registration_id"]))
        request_id = request.id
    headers = auth_headers()
    assert decide_registration(headers, request_id, "verify_identity").status_code == 200
    blocked = decide_registration(headers, request_id, "approve_role")
    assert blocked.status_code == 409
    employee = decide_registration(headers, request_id, "verify_employee", "Matched authorized employee directory record.")
    assert employee.status_code == 200
    assert decide_registration(headers, request_id, "approve_role").status_code == 200

    with SessionLocal() as db:
        verification = db.scalar(select(EmployeeVerification).where(EmployeeVerification.registration_id == request_id))
        assert verification.status == "approved"
        assert verification.method == "authorized_manual_review"
        assert verification.reviewer_id is not None
        assert verification.reviewed_at is not None
        assert verification.decision_reason


def test_institution_association_is_approved_before_membership(monkeypatch):
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution_response = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Registration Institution {suffix}", "code": f"REG-{suffix}"},
    )
    assert institution_response.status_code == 200
    institution_id = institution_response.json()["id"]
    registered, token, payload = register_request(
        monkeypatch,
        account_type="institution_user",
        institution_id=institution_id,
    )
    assert registered.status_code == 201
    assert token
    assert verify_email(token).status_code == 200

    with SessionLocal() as db:
        request = db.scalar(select(main.RegistrationRequest).where(main.RegistrationRequest.public_id == registered.json()["registration_id"]))
        request_id = request.id
    assert decide_registration(headers, request_id, "verify_identity").status_code == 200
    assert decide_registration(headers, request_id, "verify_institution").status_code == 200
    assert decide_registration(headers, request_id, "approve_role").status_code == 200

    login = client.post("/api/auth/token", data={"username": payload["username"], "password": payload["password"]})
    assert login.status_code == 200
    user_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    institution_list = client.get("/api/institutions", headers=user_headers, params={"q": suffix})
    assert [item["id"] for item in institution_list.json()] == [institution_id]


def test_github_oauth_unavailable_state_and_callback_replay(monkeypatch):
    registered, _, _ = register_request(monkeypatch)
    registration_id = registered.json()["registration_id"]
    monkeypatch.setattr(settings, "github_client_id", None)
    monkeypatch.setattr(settings, "github_client_secret", None)
    monkeypatch.setattr(settings, "github_callback_url", None)
    unavailable = client.get("/api/auth/github/start", params={"registration_id": registration_id})
    assert unavailable.status_code == 503

    monkeypatch.setattr(settings, "github_client_id", "test-client")
    monkeypatch.setattr(settings, "github_client_secret", "test-secret")
    monkeypatch.setattr(settings, "github_callback_url", "http://localhost/callback")
    start = client.get("/api/auth/github/start", params={"registration_id": registration_id})
    assert start.status_code == 200
    state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
    callback = client.get(
        "/api/auth/github/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert "github=denied" in callback.headers["location"]
    replay = client.get(
        "/api/auth/github/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert replay.status_code == 400


def test_password_reset_token_expiry_is_enforced():
    token = f"expired-{uuid.uuid4().hex}"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        db.add(AuthTokenRecord(
            user_id=user.id,
            token_hash=token_digest(token),
            purpose="password_reset",
            expires_at=datetime.now(timezone.utc).replace(microsecond=0),
        ))
        db.commit()
    expired = client.post(
        "/api/auth/password-reset/confirm",
        json={"token": token, "password": "NewVaultTracePassword123!"},
    )
    assert expired.status_code == 400


def test_configured_bootstrap_requires_token(monkeypatch):
    monkeypatch.setattr(settings, "bootstrap_token", "render-bootstrap-secret")
    monkeypatch.setattr(settings, "initial_admin_password", "A-strong-password-123")
    response = client.post("/api/auth/bootstrap")
    assert response.status_code == 403


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


def test_dashboard_recent_uploads_are_ordered_and_scoped():
    suffix = uuid.uuid4().hex[:8]
    username = f"upload-officer-{suffix}"
    with SessionLocal() as db:
        officer = User(username=username, password_hash=pwd_context.hash("UploadPass123!"), role=Role.officer)
        assigned = Institution(name=f"Upload Academy {suffix}", code=f"UPLOAD-A-{suffix}")
        hidden = Institution(name=f"Upload Hidden {suffix}", code=f"UPLOAD-B-{suffix}")
        db.add_all([officer, assigned, hidden])
        db.flush()
        db.add(UserInstitutionMembership(user_id=officer.id, institution_id=assigned.id))
        fdrs = [
            Fdr(identifier=f"FDR-UPLOAD-A-{suffix}", institution_id=assigned.id, holder_name="Assigned", amount=100,
                maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc), created_by=officer.id),
            Fdr(identifier=f"FDR-UPLOAD-B-{suffix}", institution_id=hidden.id, holder_name="Hidden", amount=200,
                maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc), created_by=officer.id),
        ]
        db.add_all(fdrs)
        db.flush()
        db.add_all([
            Document(fdr_id=fdrs[0].id, original_name="older.pdf", stored_name=f"older-{suffix}.pdf",
                     sha256=f"{suffix}a".ljust(64, "0"), content_type="application/pdf", size=1024,
                     created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            Document(fdr_id=fdrs[1].id, original_name="hidden.pdf", stored_name=f"hidden-{suffix}.pdf",
                     sha256=f"{suffix}b".ljust(64, "0"), content_type="application/pdf", size=2048,
                     created_at=datetime(2026, 1, 3, tzinfo=timezone.utc)),
            Document(fdr_id=fdrs[0].id, original_name="latest.pdf", stored_name=f"latest-{suffix}.pdf",
                     sha256=f"{suffix}c".ljust(64, "0"), content_type="application/pdf", size=3072,
                     created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        ])
        db.commit()

    token = client.post("/api/auth/token", data={"username": username, "password": "UploadPass123!"})
    assert token.status_code == 200
    scoped_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    uploads = client.get("/api/dashboard/recent-uploads?limit=1", headers=scoped_headers)
    assert uploads.status_code == 200
    assert [upload["original_name"] for upload in uploads.json()] == ["latest.pdf"]
    assert uploads.json()[0]["identifier"] == f"FDR-UPLOAD-A-{suffix}"
    assert uploads.json()[0]["status"] == "draft"


def test_institution_user_can_upload_extract_convert_and_submit_intake(monkeypatch, tmp_path):
    suffix = uuid.uuid4().hex[:8]
    username = f"document-institution-{suffix}"
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))
    with SessionLocal() as db:
        user = User(username=username, password_hash=pwd_context.hash("DocumentPass123!"), role=Role.institution_user)
        institution = Institution(name=f"Document Academy {suffix}", code=f"DOC-{suffix}")
        db.add_all([user, institution])
        db.flush()
        db.add(UserInstitutionMembership(user_id=user.id, institution_id=institution.id))
        fdr = Fdr(
            identifier=f"FDR-DOC-{suffix}",
            institution_id=institution.id,
            holder_name=institution.name,
            amount=100,
            maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
            created_by=user.id,
        )
        db.add(fdr)
        db.commit()
        fdr_id = fdr.id

    token = client.post("/api/auth/token", data={"username": username, "password": "DocumentPass123!"})
    assert token.status_code == 200
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), f"FDR number: FDR-DOC-{suffix}\nBank: Demo Bank\nAmount: 100")
    response = client.post(
        f"/api/fdrs/{fdr_id}/documents",
        headers=headers,
        files={"file": (f"synthetic-{suffix}.pdf", pdf.tobytes(), "application/pdf")},
    )
    pdf.close()
    assert response.status_code == 200
    document_id = response.json()["id"]

    extraction = client.post(f"/api/documents/{document_id}/extract", headers=headers)
    assert extraction.status_code == 200
    assert extraction.json()["text"]

    conversion = client.post(f"/api/documents/{document_id}/convert-to-fdr-draft", headers=headers)
    assert conversion.status_code == 200
    intake = client.post(
        "/api/fdr-intakes",
        headers=headers,
        json={"source_document_id": document_id, "fields": {}},
    )
    assert intake.status_code == 200
    assert intake.json()["source_fdr_id"] == fdr_id


def test_public_demo_seeder_accepts_user_data_only_after_initialization(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'public-demo.db'}")
    main.Base.metadata.create_all(engine)
    isolated_sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(public_demo_seed, "SessionLocal", isolated_sessions)
    with isolated_sessions() as db:
        user = User(username="visitor-created-user", password_hash="hash", role=Role.viewer)
        institution = Institution(name="Visitor Created College", code="VISITOR-COLLEGE")
        db.add_all([user, institution])
        db.flush()
        db.add(Fdr(
            identifier="VISITOR-FDR-001",
            institution_id=institution.id,
            holder_name=institution.name,
            amount=100,
            maturity_date=datetime(2027, 1, 1, tzinfo=timezone.utc),
            created_by=user.id,
        ))
        db.commit()

    with pytest.raises(RuntimeError, match="non-demo users"):
        public_demo_seed._seed_demo_directory_and_accounts()

    with isolated_sessions() as db:
        db.execute(public_demo_seed.PUBLIC_DEMO_STATE.insert().values(key="initialized", value="true"))
        db.commit()

    public_demo_seed._seed_demo_directory_and_accounts()

    with isolated_sessions() as db:
        assert db.scalar(select(User.id).where(User.username == "visitor-created-user")) is not None
        assert db.scalar(select(Fdr.id).where(Fdr.identifier == "VISITOR-FDR-001")) is not None
        assert db.scalar(select(User.id).where(User.username == "demo_administrator")) is not None


def test_public_demo_registration_samples_are_synthetic_and_idempotent(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'registration-samples.db'}")
    main.Base.metadata.create_all(engine)
    isolated_sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(public_demo_seed, "SessionLocal", isolated_sessions)
    monkeypatch.setattr(settings, "upload_dir", str(upload_dir))

    public_demo_seed._seed_demo_directory_and_accounts()
    public_demo_seed._seed_registration_samples()
    public_demo_seed._seed_registration_samples()

    with isolated_sessions() as db:
        samples = db.scalars(
            select(public_demo_seed.RegistrationRequest).order_by(
                public_demo_seed.RegistrationRequest.username
            )
        ).all()
        assert len(samples) == 4
        assert sum(sample.status not in {"approved", "rejected"} for sample in samples) == 3
        assert all(sample.email.endswith("@vaulttrace.invalid") for sample in samples)
        assert all(sample.identity_document_stored_name for sample in samples)
        assert db.scalar(select(EmployeeVerification.id)) is not None
        assert db.scalar(select(RegistrationAuditEvent.id)) is not None

    placeholder = upload_dir / "demo-synthetic-identity-placeholder.png"
    assert placeholder.is_file()
    with Image.open(placeholder) as image:
        assert image.size == (720, 420)
        assert image.format == "PNG"
    engine.dispose()


def test_public_demo_allows_authorized_writes_and_keeps_authentication(monkeypatch):
    monkeypatch.setattr(main.settings, "public_demo_mode", True)

    unauthorized = client.post("/api/institutions", json={"name": "Demo Academy", "code": f"UNAUTH-{uuid.uuid4().hex[:8]}"})
    assert unauthorized.status_code == 401

    created = client.post(
        "/api/institutions",
        headers=auth_headers(),
        json={"name": "Shared Demo Academy", "code": f"PUBLIC-WRITE-{uuid.uuid4().hex[:8]}"},
    )
    assert created.status_code == 200
    assert created.json()["name"] == "Shared Demo Academy"

    login = client.post("/api/auth/token", data={"username": "not-a-demo-user", "password": "invalid"})
    assert login.status_code == 401


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


def test_discrepancy_analysis_is_scoped_and_review_actions_are_audited():
    headers = auth_headers()
    suffix = uuid.uuid4().hex[:8]
    institution = client.post(
        "/api/institutions",
        headers=headers,
        json={"name": f"Analysis Academy {suffix}", "code": f"ANALYSIS-{suffix}"},
    )
    assert institution.status_code == 200

    def create_fdr(identifier: str):
        response = client.post("/api/fdrs", headers=headers, json={
            "identifier": identifier,
            "institution_id": institution.json()["id"],
            "holder_name": "Stored Holder",
            "approval_case_reference": f"CASE-{suffix}",
            "bank_name": "Example Bank",
            "branch_name": "Main Branch",
            "ifsc_code": "SBIN0001234",
            "amount": 100000,
            "amount_in_words": "Rupees One Lakh Only",
            "issue_date": "2026-01-01T00:00:00Z",
            "maturity_date": "2027-01-01T00:00:00Z",
            "beneficiary": "VaultTrace Authority",
            "joint_holder": "Stored Holder",
            "lien_endorsed": False,
        })
        assert response.status_code == 200
        return response.json()

    first = create_fdr(f"FDR-ANALYSIS-{suffix}")
    second = create_fdr(f"FDR-ISOLATED-{suffix}")
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text(
        (72, 72),
        f"FDR number: FDR-OCR-DIFFERENT-{suffix}\nHolder Name: OCR Holder\nAmount: 250000",
    )
    content = pdf.tobytes()
    pdf.close()
    uploaded = client.post(
        f"/api/fdrs/{first['id']}/documents",
        headers=headers,
        files={"file": (f"analysis-{suffix}.pdf", io.BytesIO(content), "application/pdf")},
    )
    assert uploaded.status_code == 200
    extraction = client.post(f"/api/documents/{uploaded.json()['id']}/extract", headers=headers)
    assert extraction.status_code == 200

    analysis = client.post(f"/api/fdrs/{first['id']}/discrepancies/analyze", headers=headers)
    assert analysis.status_code == 200
    payload = analysis.json()
    assert payload["analysis_method"] == "rule_based"
    amount_finding = next(item for item in payload["findings"] if item["rule_id"].startswith("AUTO:OCR_MISMATCH:amount"))
    assert amount_finding["fdr_id"] == first["id"]
    assert amount_finding["expected_value"] == "100000.0"
    assert amount_finding["observed_value"] == "250000"
    assert "OCR" in amount_finding["observed_source"]
    assert f"Document #{uploaded.json()['id']}" in amount_finding["evidence_reference"]
    assert amount_finding["evidence_document_ids"] == [uploaded.json()["id"]]
    repeated = client.post(f"/api/fdrs/{first['id']}/discrepancies/analyze", headers=headers)
    assert repeated.status_code == 200
    assert {item["rule_id"] for item in repeated.json()["findings"]} == {
        item["rule_id"] for item in payload["findings"]
    }

    chat = client.post(
        f"/api/fdrs/{first['id']}/discrepancies/chat",
        headers=headers,
        json={"question": "Does the amount match?"},
    )
    assert chat.status_code == 200
    assert chat.json()["analysis_method"] == "rule_based"
    assert chat.json()["fdr_id"] == first["id"]
    assert "100,000.00" in chat.json()["reply"]
    assert "250000" in chat.json()["reply"]
    assert f"Finding #{amount_finding['id']}" in chat.json()["reply"]
    assert any("document #" in source.casefold() for source in chat.json()["sources"])

    invalid_chat = client.post(
        f"/api/fdrs/{first['id']}/discrepancies/chat",
        headers=headers,
        json={"question": "x"},
    )
    assert invalid_chat.status_code == 422

    isolated = client.post(f"/api/fdrs/{second['id']}/discrepancies/analyze", headers=headers)
    assert isolated.status_code == 200
    assert all(item["fdr_id"] == second["id"] for item in isolated.json()["findings"])
    assert not any(item["rule_id"].startswith("AUTO:OCR_MISMATCH") for item in isolated.json()["findings"])
    unavailable_comparison = client.post(
        f"/api/fdrs/{second['id']}/discrepancies/chat",
        headers=headers,
        json={"question": "Does the amount match?"},
    )
    assert unavailable_comparison.status_code == 200
    assert "does not confirm the field was checked" in unavailable_comparison.json()["reply"]

    reviewed = client.post(
        f"/api/discrepancies/{amount_finding['id']}/review",
        headers=headers,
        json={"action": "mark_reviewed", "reason": "Compared against the attached receipt."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "reviewed"
    assert reviewed.json()["history"][-1]["action"] == "mark_reviewed"

    dismissed = client.post(
        f"/api/discrepancies/{amount_finding['id']}/review",
        headers=headers,
        json={"action": "dismiss", "reason": "The OCR amount was misread; the source is consistent."},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["review_status"] == "dismissed"
    assert dismissed.json()["status"] == "resolved"
    assert len(dismissed.json()["history"]) == 2

    reopened = client.post(
        f"/api/discrepancies/{amount_finding['id']}/review",
        headers=headers,
        json={"action": "confirm", "reason": "A second reviewer confirmed the amount mismatch."},
    )
    assert reopened.status_code == 200
    assert reopened.json()["review_status"] == "confirmed"
    assert reopened.json()["status"] == "open"

    missing = client.post("/api/fdrs/2147483647/discrepancies/analyze", headers=headers)
    assert missing.status_code == 404

    reviewer_name = f"analysis-reviewer-{suffix}"
    with SessionLocal() as db:
        db.add(User(
            username=reviewer_name,
            password_hash=pwd_context.hash("ReviewPass123!"),
            role=Role.reviewer,
        ))
        db.commit()
    reviewer_token = client.post(
        "/api/auth/token",
        data={"username": reviewer_name, "password": "ReviewPass123!"},
    )
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token.json()['access_token']}"}
    denied = client.post(
        f"/api/discrepancies/{amount_finding['id']}/review",
        headers=reviewer_headers,
        json={"action": "confirm", "reason": "No institution access."},
    )
    assert denied.status_code == 403
    denied_chat = client.post(
        f"/api/fdrs/{first['id']}/discrepancies/chat",
        headers=reviewer_headers,
        json={"question": "Summarize findings"},
    )
    assert denied_chat.status_code == 403
