from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Annotated, Generator, Optional
import hashlib
import csv
import io
import json
import secrets
import smtplib
import uuid
import shutil
import re
import httpx
import fitz
import pytesseract
from PIL import Image, ImageOps
from email.message import EmailMessage

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.exc import SQLAlchemyError


class Settings(BaseSettings):
    database_url: str = "sqlite:///./vaulttrace.db"
    secret_key: str = "change-me"
    access_token_minutes: int = 60
    upload_dir: str = "./private_uploads"
    max_upload_bytes: int = 10 * 1024 * 1024
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    bootstrap_token: str | None = None
    initial_admin_password: str | None = None
    app_environment: str = "development"
    public_demo_mode: bool = False
    frontend_base_url: str = "http://localhost:5173"
    email_verification_base_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    github_callback_url: str | None = None
    tesseract_cmd: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    admin = "admin"
    officer = "officer"
    reviewer = "reviewer"
    viewer = "viewer"
    custody = "custody"
    auditor = "auditor"
    policy_admin = "policy_admin"
    institution_user = "institution_user"
    verification_officer = "verification_officer"


class RegistrationAccountType(str, Enum):
    institution_user = "institution_user"
    reviewing_officer = "reviewing_officer"
    verification_officer = "verification_officer"
    custody_officer = "custody_officer"
    policy_administrator = "policy_administrator"
    auditor = "auditor"
    administrator = "administrator"
    viewer = "viewer"


ACCOUNT_TYPE_ROLES = {
    RegistrationAccountType.institution_user: Role.institution_user,
    RegistrationAccountType.reviewing_officer: Role.reviewer,
    RegistrationAccountType.verification_officer: Role.verification_officer,
    RegistrationAccountType.custody_officer: Role.custody,
    RegistrationAccountType.policy_administrator: Role.policy_admin,
    RegistrationAccountType.auditor: Role.auditor,
    RegistrationAccountType.administrator: Role.admin,
    RegistrationAccountType.viewer: Role.viewer,
}


class FdrStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    under_review = "under_review"
    verified = "verified"
    release_requested = "release_requested"
    approved = "approved"
    rejected = "rejected"
    executed = "executed"
    closed = "closed"


class VerificationStatus(str, Enum):
    pending = "pending"
    in_review = "in_review"
    clarification = "clarification"
    verified = "verified"
    rejected = "rejected"


class DiscrepancyStatus(str, Enum):
    open = "open"
    resolved = "resolved"
    waived = "waived"


class DiscrepancyReviewAction(str, Enum):
    mark_reviewed = "mark_reviewed"
    confirm = "confirm"
    dismiss = "dismiss"
    add_note = "add_note"
    request_evidence = "request_evidence"
    escalate = "escalate"


class ProvenanceLevel(str, Enum):
    declared = "L0"
    extracted = "L1"
    reviewed = "L2"
    independently_confirmed = "L3"


class ReleaseType(str, Enum):
    release = "release"
    refund = "refund"


class InstrumentChangeType(str, Enum):
    renewal = "renewal"
    replacement = "replacement"


class ImportStatus(str, Enum):
    preview = "preview"
    imported = "imported"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SqlEnum(Role), default=Role.viewer)
    active: Mapped[bool] = mapped_column(default=True)


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    account_type: Mapped[str] = mapped_column(String(40))
    organization_name: Mapped[str] = mapped_column(String(255), default="")
    institution_id: Mapped[Optional[int]] = mapped_column(ForeignKey("institutions.id"), nullable=True, index=True)
    employee_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    department: Mapped[str] = mapped_column(String(150), default="")
    designation: Mapped[str] = mapped_column(String(150), default="")
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    identity_status: Mapped[str] = mapped_column(String(30), default="pending")
    employee_status: Mapped[str] = mapped_column(String(30), default="not_required")
    institution_status: Mapped[str] = mapped_column(String(30), default="not_required")
    role_status: Mapped[str] = mapped_column(String(30), default="pending")
    status: Mapped[str] = mapped_column(String(50), default="pending_email_verification", index=True)
    github_provider_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    github_login: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    github_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    identity_document_stored_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    identity_document_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    identity_document_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    identity_document_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    identity_document_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decision_actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EmployeeVerification(Base):
    __tablename__ = "employee_verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registration_requests.id"), unique=True, index=True)
    employee_id: Mapped[str] = mapped_column(String(100), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    official_email: Mapped[str] = mapped_column(String(320))
    organization_name: Mapped[str] = mapped_column(String(255))
    department: Mapped[str] = mapped_column(String(150))
    designation: Mapped[str] = mapped_column(String(150))
    requested_role: Mapped[str] = mapped_column(String(40))
    method: Mapped[str] = mapped_column(String(40), default="manual_review")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    evidence_reference: Mapped[str] = mapped_column(String(500), default="")
    reviewer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuthTokenRecord(Base):
    __tablename__ = "auth_token_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[Optional[int]] = mapped_column(ForeignKey("registration_requests.id"), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GithubOAuthState(Base):
    __tablename__ = "github_oauth_states"
    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registration_requests.id"), index=True)
    state_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RegistrationAuditEvent(Base):
    __tablename__ = "registration_audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registration_requests.id"), index=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    previous_status: Mapped[str] = mapped_column(String(50), default="")
    new_status: Mapped[str] = mapped_column(String(50), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserInstitutionMembership(Base):
    __tablename__ = "user_institution_memberships"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    address: Mapped[str] = mapped_column(Text, default="")
    aicte_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=True, index=True)
    other_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    district: Mapped[str] = mapped_column(String(150), default="", index=True)
    state: Mapped[str] = mapped_column(String(150), default="", index=True)
    institution_type: Mapped[str] = mapped_column(String(100), default="", index=True)
    women: Mapped[str] = mapped_column(String(10), default="")
    minority: Mapped[str] = mapped_column(String(10), default="")
    university: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    fdrs: Mapped[list["Fdr"]] = relationship(back_populates="institution")
    programmes: Mapped[list["InstitutionProgramme"]] = relationship(back_populates="institution", cascade="all, delete-orphan")


class InstitutionProgramme(Base):
    __tablename__ = "institution_programmes"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"), index=True)
    programme: Mapped[str] = mapped_column(String(255), default="")
    level: Mapped[str] = mapped_column(String(100), default="")
    course: Mapped[str] = mapped_column(String(255), default="")
    course_type: Mapped[str] = mapped_column(String(150), default="")
    shift: Mapped[str] = mapped_column(String(100), default="")
    availability: Mapped[str] = mapped_column(String(100), default="")
    intake: Mapped[str] = mapped_column(String(50), default="")
    enrollment: Mapped[str] = mapped_column(String(50), default="")
    placement: Mapped[str] = mapped_column(String(50), default="")
    institution: Mapped[Institution] = relationship(back_populates="programmes")


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    required_documents: Mapped[str] = mapped_column(Text, default="[]")
    amount_floor: Mapped[float] = mapped_column(default=0)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expiry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(default=1)
    active: Mapped[bool] = mapped_column(default=False)
    source_reference: Mapped[str] = mapped_column(String(500), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class DepositAssessment(Base):
    __tablename__ = "deposit_assessments"
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    policy_rule_id: Mapped[int] = mapped_column(ForeignKey("policy_rules.id"), nullable=True)
    amount: Mapped[float] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="policy_required")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[ImportStatus] = mapped_column(SqlEnum(ImportStatus))
    row_count: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    valid_rows: Mapped[str] = mapped_column(Text, default="[]")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ImportRowError(Base):
    __tablename__ = "import_row_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"))
    row_number: Mapped[int]
    message: Mapped[str] = mapped_column(Text)
    raw_data: Mapped[str] = mapped_column(Text)


class Fdr(Base):
    __tablename__ = "fdrs"
    id: Mapped[int] = mapped_column(primary_key=True)
    identifier: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("institutions.id"))
    holder_name: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float]
    approval_case_reference: Mapped[str] = mapped_column(String(100), nullable=True)
    bank_name: Mapped[str] = mapped_column(String(255), nullable=True)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=True)
    ifsc_code: Mapped[str] = mapped_column(String(20), nullable=True)
    amount_in_words: Mapped[str] = mapped_column(String(500), nullable=True)
    issue_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    beneficiary: Mapped[str] = mapped_column(String(500), nullable=True)
    joint_holder: Mapped[str] = mapped_column(String(255), nullable=True)
    lien_endorsed: Mapped[bool] = mapped_column(default=False)
    lien_clause: Mapped[str] = mapped_column(Text, nullable=True)
    maturity_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[FdrStatus] = mapped_column(SqlEnum(FdrStatus), default=FdrStatus.draft)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    institution: Mapped[Institution] = relationship(back_populates="fdrs")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ExtractionResult(Base):
    __tablename__ = "extraction_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    provider: Mapped[str] = mapped_column(String(100), default="local-pymupdf")
    status: Mapped[str] = mapped_column(String(30), default="completed")
    page_count: Mapped[int] = mapped_column(default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    authenticity_confirmed: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FdrIntake(Base):
    __tablename__ = "fdr_intakes"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    source_fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"), index=True)
    candidate_fields: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(40), default="pending_completion")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fdr_id: int
    original_name: str
    sha256: str
    content_type: str
    size: int
    created_at: datetime


class RecentUploadOut(BaseModel):
    id: int
    fdr_id: int
    identifier: str
    original_name: str
    content_type: str
    size: int
    created_at: datetime
    status: FdrStatus


class InstrumentVersion(Base):
    __tablename__ = "instrument_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    version_number: Mapped[int]
    source_version_id: Mapped[int] = mapped_column(ForeignKey("instrument_versions.id"), nullable=True)
    change_reason: Mapped[str] = mapped_column(String(500))
    snapshot: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FieldProvenance(Base):
    __tablename__ = "field_provenance"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    field_name: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    level: Mapped[ProvenanceLevel] = mapped_column(SqlEnum(ProvenanceLevel))
    source_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=True)
    evidence_reference: Mapped[str] = mapped_column(String(500), default="")
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Discrepancy(Base):
    __tablename__ = "discrepancies"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    rule_id: Mapped[str] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    explanation: Mapped[str] = mapped_column(Text)
    expected_value: Mapped[str] = mapped_column(Text, default="")
    observed_value: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[DiscrepancyStatus] = mapped_column(SqlEnum(DiscrepancyStatus), default=DiscrepancyStatus.open)
    resolution_notes: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DiscrepancyAnalysisDetail(Base):
    __tablename__ = "discrepancy_analysis_details"
    discrepancy_id: Mapped[int] = mapped_column(ForeignKey("discrepancies.id"), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    affected_field: Mapped[str] = mapped_column(String(100), default="")
    expected_source: Mapped[str] = mapped_column(String(500), default="")
    observed_source: Mapped[str] = mapped_column(String(500), default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    evidence_reference: Mapped[str] = mapped_column(String(1000), default="")
    analysis_method: Mapped[str] = mapped_column(String(50), default="rule_based")
    review_status: Mapped[str] = mapped_column(String(40), default="pending")


class DiscrepancyReviewEvent(Base):
    __tablename__ = "discrepancy_review_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    discrepancy_id: Mapped[int] = mapped_column(ForeignKey("discrepancies.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class VerificationCase(Base):
    __tablename__ = "verification_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"), unique=True)
    status: Mapped[VerificationStatus] = mapped_column(SqlEnum(VerificationStatus), default=VerificationStatus.pending)
    assigned_to: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    outcome_notes: Mapped[str] = mapped_column(Text, default="")
    evidence_reference: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReleaseRequest(Base):
    __tablename__ = "release_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    request_type: Mapped[ReleaseType] = mapped_column(SqlEnum(ReleaseType))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    entity: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100))
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LifecycleEvent(Base):
    __tablename__ = "lifecycle_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    from_status: Mapped[str] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CustodyEvent(Base):
    __tablename__ = "custody_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    location: Mapped[str] = mapped_column(String(255))
    custodian: Mapped[str] = mapped_column(String(255))
    evidence_reference: Mapped[str] = mapped_column(String(500), default="")
    remarks: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class NotificationEvent(Base):
    __tablename__ = "notification_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    fdr_id: Mapped[int] = mapped_column(ForeignKey("fdrs.id"))
    channel: Mapped[str] = mapped_column(String(30))
    reminder_days: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="planned")
    recipient: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app = FastAPI(title="VaultTrace API", version="1.0.0")
allowed_origins = [
    origin if "://" in origin else f"https://{origin}"
    for value in settings.cors_origins.split(",")
    if (origin := value.strip().rstrip("/"))
]
app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def restrict_public_demo_writes(request: Request, call_next):
    state_changing_get_routes = {
        "/api/auth/github/start",
        "/api/auth/github/callback",
    }
    if (
        settings.public_demo_mode
        and (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.url.path != "/api/auth/token"
            or request.method in {"GET", "HEAD"}
            and request.url.path in state_changing_get_routes
        )
    ):
        return JSONResponse(status_code=403, content={"detail": "This public demo is read-only."})
    return await call_next(request)


def initialize_public_demo() -> None:
    if not settings.public_demo_mode:
        return
    if settings.app_environment.casefold() != "demo":
        raise RuntimeError("PUBLIC_DEMO_MODE requires APP_ENVIRONMENT=demo.")
    from .seed_public_demo import seed_public_demo

    seed_public_demo()


app.add_event_handler("startup", initialize_public_demo)


def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


Db = Annotated[Session, Depends(db_session)]


def token_for(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(user.id), "role": user.role.value, "exp": exp}, settings.secret_key, algorithm="HS256")


def current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Db) -> User:
    credentials = HTTPException(status_code=401, detail="Invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = int(payload.get("sub", ""))
    except (JWTError, ValueError):
        raise credentials
    user = db.get(User, user_id)
    if not user or not user.active:
        raise credentials
    return user


def require_roles(*roles: Role):
    def dependency(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user
    return dependency


def require_institution_access(db: Session, user: User, institution_id: int) -> None:
    if user.role in {Role.admin, Role.auditor}:
        return
    assigned = db.scalar(
        select(UserInstitutionMembership.id).where(
            UserInstitutionMembership.user_id == user.id,
            UserInstitutionMembership.institution_id == institution_id,
        )
    )
    if assigned is None:
        raise HTTPException(status_code=403, detail="User is not assigned to this institution")


def require_fdr_access(db: Session, user: User, fdr_id: int) -> Fdr:
    fdr = db.get(Fdr, fdr_id)
    if not fdr:
        raise HTTPException(status_code=404, detail="FDR not found")
    require_institution_access(db, user, fdr.institution_id)
    return fdr


def can_change_status(user: User, current: FdrStatus, target: FdrStatus) -> bool:
    if user.role == Role.admin:
        return True
    transitions = {
        Role.institution_user: {
            FdrStatus.draft: {FdrStatus.submitted},
            FdrStatus.verified: {FdrStatus.release_requested},
        },
        Role.officer: {
            FdrStatus.draft: {FdrStatus.submitted},
            FdrStatus.verified: {FdrStatus.release_requested},
        },
        Role.reviewer: {
            FdrStatus.submitted: {FdrStatus.under_review, FdrStatus.rejected},
            FdrStatus.under_review: {FdrStatus.verified, FdrStatus.rejected},
            FdrStatus.release_requested: {FdrStatus.approved, FdrStatus.rejected},
            FdrStatus.executed: {FdrStatus.closed},
        },
    }
    return target in transitions.get(user.role, {}).get(current, set())


class Token(BaseModel):
    access_token: str
    token_type: str


class RegistrationIn(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    password_confirmation: str = Field(min_length=12, max_length=128)
    account_type: RegistrationAccountType
    organization_name: str = Field(default="", max_length=255)
    institution_id: int | None = None
    employee_id: str | None = Field(default=None, max_length=100)
    department: str = Field(default="", max_length=150)
    designation: str = Field(default="", max_length=150)
    consent: bool

    @model_validator(mode="after")
    def validate_registration(self):
        if self.password != self.password_confirmation:
            raise ValueError("Password confirmation does not match")
        if not self.consent:
            raise ValueError("Registration consent is required")
        if self.account_type == RegistrationAccountType.institution_user and not self.institution_id:
            raise ValueError("Select the institution you are requesting to join")
        if self.account_type not in {RegistrationAccountType.institution_user, RegistrationAccountType.viewer}:
            if not self.employee_id or not self.organization_name.strip() or not self.department.strip() or not self.designation.strip():
                raise ValueError("Employee ID, organization, department and designation are required for this account type")
        return self


class RegistrationResubmitIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    full_name: str = Field(min_length=2, max_length=200)
    organization_name: str = Field(default="", max_length=255)
    institution_id: int | None = None
    employee_id: str | None = Field(default=None, max_length=100)
    department: str = Field(default="", max_length=150)
    designation: str = Field(default="", max_length=150)


class RegistrationStatusOut(BaseModel):
    registration_id: str
    account_type: str
    status: str
    email_verification: str
    identity_verification: str
    employee_verification: str
    institution_association: str
    role_approval: str
    updated_at: datetime
    decision_reason: str = ""


class RegistrationDecisionIn(BaseModel):
    action: str = Field(pattern=r"^(verify_identity|verify_employee|verify_institution|approve_role|reject)$")
    reason: str = Field(min_length=3, max_length=2000)
    evidence_reference: str = Field(default="", max_length=500)


class RegistrationStatusLookupIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class PasswordResetRequestIn(BaseModel):
    email: str = Field(min_length=5, max_length=320)


class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    password: str = Field(min_length=12, max_length=128)


class OneTimeTokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class GitHubOAuthStartOut(BaseModel):
    authorization_url: str


class AdminUserOut(BaseModel):
    id: int
    username: str
    email: str | None
    role: Role
    active: bool


class UserActivationIn(BaseModel):
    active: bool
    reason: str = Field(min_length=3, max_length=2000)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    email: str | None = None


class InstitutionIn(BaseModel):
    name: str = Field(min_length=2)
    code: str = Field(min_length=2, max_length=50)
    address: str = ""


class MembershipIn(BaseModel):
    user_id: int
    institution_id: int


class InstitutionOut(InstitutionIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    aicte_id: str | None = None
    other_id: str | None = None
    district: str = ""
    state: str = ""
    institution_type: str = ""
    women: str = ""
    minority: str = ""
    university: str = ""


class ProgrammeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    programme: str
    level: str
    course: str
    course_type: str
    shift: str
    availability: str
    intake: str
    enrollment: str
    placement: str


class FdrIn(BaseModel):
    identifier: str = Field(min_length=3)
    institution_id: int
    holder_name: str = Field(min_length=2)
    amount: float = Field(gt=0)
    approval_case_reference: str = Field(min_length=2)
    bank_name: str = Field(min_length=2)
    branch_name: str = Field(min_length=2)
    ifsc_code: str = Field(min_length=8, max_length=11, pattern=r"^[A-Z]{4}0[A-Z0-9]{6}$")
    amount_in_words: str = Field(min_length=2)
    issue_date: datetime
    beneficiary: str = Field(min_length=2)
    joint_holder: str = Field(min_length=2)
    lien_endorsed: bool = False
    lien_clause: str = ""
    maturity_date: datetime

    @model_validator(mode="after")
    def validate_registration(self):
        if self.issue_date and self.maturity_date <= self.issue_date:
            raise ValueError("Maturity date must be after issue date")
        if self.lien_endorsed and len(self.lien_clause.strip()) < 5:
            raise ValueError("Lien clause is required when lien endorsement is selected")
        return self


class FdrIntakeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str | None = Field(default=None, max_length=100)
    institution_id: str | None = Field(default=None, max_length=20)
    approval_case_reference: str | None = Field(default=None, max_length=100)
    bank_name: str | None = Field(default=None, max_length=255)
    branch_name: str | None = Field(default=None, max_length=255)
    ifsc_code: str | None = Field(default=None, max_length=20)
    amount: str | None = Field(default=None, max_length=50)
    amount_in_words: str | None = Field(default=None, max_length=500)
    issue_date: str | None = Field(default=None, max_length=40)
    maturity_date: str | None = Field(default=None, max_length=40)
    beneficiary: str | None = Field(default=None, max_length=500)
    joint_holder: str | None = Field(default=None, max_length=255)
    lien_endorsed: bool = False
    lien_clause: str = Field(default="", max_length=2000)


class FdrIntakeIn(BaseModel):
    source_document_id: int
    fields: FdrIntakeFields


class FdrIntakeOut(BaseModel):
    id: int
    source_document_id: int
    source_fdr_id: int
    candidate_fields: dict[str, str | bool]
    status: str
    created_at: datetime


class FdrOut(FdrIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: FdrStatus
    approval_case_reference: str | None = None
    bank_name: str | None = None
    branch_name: str | None = None
    ifsc_code: str | None = None
    amount_in_words: str | None = None
    issue_date: datetime | None = None
    beneficiary: str | None = None
    joint_holder: str | None = None
    lien_clause: str | None = None


class StatusChange(BaseModel):
    status: FdrStatus


class InstrumentChangeIn(BaseModel):
    change_type: InstrumentChangeType
    reason: str = Field(min_length=10)
    proposed_identifier: str = Field(min_length=3)
    proposed_maturity_date: datetime


class PolicyIn(BaseModel):
    rule_id: str = Field(min_length=2)
    description: str = Field(min_length=5)
    required_documents: list[str] = []
    amount_floor: float = Field(default=0, ge=0)
    effective_date: datetime
    expiry_date: datetime | None = None
    version: int = Field(default=1, ge=1)
    active: bool = False
    source_reference: str = ""


class PolicyStatusIn(BaseModel):
    active: bool


class AssessmentIn(BaseModel):
    institution_id: int
    policy_rule_id: int | None = None
    amount: float | None = Field(default=None, gt=0)
    notes: str = ""


class ProvenanceIn(BaseModel):
    field_name: str = Field(min_length=1)
    value: str
    level: ProvenanceLevel
    source_document_id: int | None = None
    evidence_reference: str = ""


class DiscrepancyIn(BaseModel):
    rule_id: str = Field(min_length=1)
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    explanation: str = Field(min_length=5)
    expected_value: str = ""
    observed_value: str = ""


class ResolutionIn(BaseModel):
    status: DiscrepancyStatus
    resolution_notes: str = Field(min_length=5)


class DiscrepancyReviewIn(BaseModel):
    action: DiscrepancyReviewAction
    reason: str = Field(min_length=3, max_length=2000)


class DiscrepancyChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class VerificationIn(BaseModel):
    status: VerificationStatus
    outcome_notes: str = Field(min_length=5)
    evidence_reference: str = ""


class ReleaseRequestIn(BaseModel):
    request_type: ReleaseType
    reason: str = Field(min_length=10)


class DecisionIn(BaseModel):
    approved: bool
    decision_notes: str = Field(min_length=5)


class ExecutionIn(BaseModel):
    evidence_reference: str = Field(min_length=3)
    execution_notes: str = Field(min_length=5)


class CustodyIn(BaseModel):
    event_type: str = Field(pattern="^(received|transferred|released|returned)$")
    location: str = Field(min_length=2)
    custodian: str = Field(min_length=2)
    evidence_reference: str = ""
    remarks: str = ""


class NotificationIn(BaseModel):
    channel: str = Field(pattern="^(email|sms|in_app)$")
    reminder_days: int = Field(ge=0, le=3650)
    recipient: str = Field(min_length=2)


class NotificationStatusIn(BaseModel):
    status: str = Field(pattern="^(unavailable)$")
    reason: str = Field(min_length=5)


class InstrumentVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    fdr_id: int
    version_number: int
    source_version_id: int | None
    change_reason: str
    snapshot: str


@app.get("/health")
def health(db: Db):
    db.execute(select(func.count(User.id))).scalar_one()
    return {"status": "ok", "database": "connected"}


def normalized_email(value: str) -> str:
    email = value.strip().casefold()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    return email


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def normalized_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    return value if re.match(r"^https?://", value, re.IGNORECASE) else f"https://{value}"


def send_account_email(recipient: str, subject: str, body: str) -> bool:
    if not settings.smtp_host or not settings.smtp_from_email:
        return False
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    if settings.smtp_port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(message)
    return True


def issue_auth_token(
    db: Session,
    purpose: str,
    registration_id: int | None = None,
    user_id: int | None = None,
    lifetime: timedelta = timedelta(hours=24),
) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthTokenRecord(
        registration_id=registration_id,
        user_id=user_id,
        token_hash=token_digest(token),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + lifetime,
    ))
    return token


def registration_status(request: RegistrationRequest) -> str:
    if request.status == "rejected":
        return "rejected"
    if request.email_verified_at is None:
        return "pending_email_verification"
    if request.identity_status != "approved":
        return "pending_identity_verification"
    if request.employee_status not in {"approved", "not_required"}:
        return "pending_employee_verification"
    if request.institution_status not in {"approved", "not_required"}:
        return "pending_organization_verification"
    if request.role_status != "approved":
        return "pending_role_approval"
    return "approved"


def update_registration_status(request: RegistrationRequest) -> str:
    previous = request.status
    request.status = registration_status(request)
    request.updated_at = datetime.now(timezone.utc)
    return previous


def registration_status_payload(request: RegistrationRequest) -> RegistrationStatusOut:
    return RegistrationStatusOut(
        registration_id=request.public_id,
        account_type=request.account_type,
        status=request.status,
        email_verification="verified" if request.email_verified_at else "pending",
        identity_verification=request.identity_status,
        employee_verification=request.employee_status,
        institution_association=request.institution_status,
        role_approval=request.role_status,
        updated_at=request.updated_at,
        decision_reason=request.decision_reason,
    )


def add_registration_audit(
    db: Session,
    request: RegistrationRequest,
    actor_id: int | None,
    action: str,
    previous_status: str,
    reason: str = "",
) -> None:
    db.add(RegistrationAuditEvent(
        registration_id=request.id,
        actor_id=actor_id,
        action=action,
        previous_status=previous_status,
        new_status=request.status,
        reason=reason,
    ))


@app.post("/api/auth/token", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not pwd_context.verify(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    return {"access_token": token_for(user), "token_type": "bearer"}


@app.get("/api/auth/me", response_model=UserOut)
def me(user: Annotated[User, Depends(current_user)]):
    return user


@app.get("/api/auth/registration-institutions")
def registration_institutions(db: Db):
    return db.execute(
        select(Institution.id, Institution.name, Institution.code).order_by(Institution.name).limit(1000)
    ).mappings().all()


MAX_IDENTITY_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IDENTITY_IMAGE_PIXELS = 12_000_000


def sanitize_identity_image(upload: UploadFile | None) -> tuple[bytes, str, str] | None:
    if upload is None:
        return None
    content = upload.file.read(MAX_IDENTITY_IMAGE_BYTES + 1)
    if len(content) > MAX_IDENTITY_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="ID card image must be 5 MB or smaller")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            if image_format not in {"JPEG", "PNG"}:
                raise HTTPException(status_code=415, detail="Upload an ID card image in JPEG or PNG format")
            if width < 1 or height < 1 or width * height > MAX_IDENTITY_IMAGE_PIXELS:
                raise HTTPException(status_code=413, detail="ID card image dimensions exceed the allowed limit")
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            oriented_image = ImageOps.exif_transpose(image)
            clean_image = oriented_image.convert("RGB" if image_format == "JPEG" else "RGBA" if "A" in oriented_image.getbands() else "RGB")
            output = io.BytesIO()
            clean_image.save(output, format=image_format, optimize=True)
    except HTTPException:
        raise
    except (Image.DecompressionBombError, OSError, ValueError) as error:
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid JPEG or PNG image") from error
    extension = "jpg" if image_format == "JPEG" else "png"
    content_type = "image/jpeg" if image_format == "JPEG" else "image/png"
    clean_content = output.getvalue()
    if len(clean_content) > MAX_IDENTITY_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Processed ID card image exceeds the 5 MB limit")
    return clean_content, content_type, extension


def create_registration(
    data: RegistrationIn,
    db: Session,
    identity_image: tuple[bytes, str, str] | None = None,
):
    email = normalized_email(data.email)
    username = data.username.strip().casefold()
    if db.scalar(select(User.id).where(User.username == username)) or db.scalar(
        select(RegistrationRequest.id).where(RegistrationRequest.username == username)
    ):
        raise HTTPException(status_code=409, detail="That username is already in use")
    if db.scalar(select(User.id).where(User.email == email)) or db.scalar(
        select(RegistrationRequest.id).where(RegistrationRequest.email == email)
    ):
        raise HTTPException(status_code=409, detail="An account or request already uses that email")
    if data.employee_id and db.scalar(
        select(EmployeeVerification.id).where(EmployeeVerification.employee_id == data.employee_id.strip())
    ):
        raise HTTPException(status_code=409, detail="That employee ID is already under verification")
    institution = db.get(Institution, data.institution_id) if data.institution_id else None
    if data.institution_id and not institution:
        raise HTTPException(status_code=404, detail="Selected institution was not found")

    account_type = data.account_type
    employee_required = account_type not in {
        RegistrationAccountType.institution_user,
        RegistrationAccountType.viewer,
    }
    request = RegistrationRequest(
        public_id=str(uuid.uuid4()),
        username=username,
        full_name=data.full_name.strip(),
        email=email,
        password_hash=pwd_context.hash(data.password),
        account_type=account_type.value,
        organization_name=(institution.name if institution else data.organization_name.strip()),
        institution_id=institution.id if institution else None,
        employee_id=data.employee_id.strip() if employee_required and data.employee_id else None,
        department=data.department.strip(),
        designation=data.designation.strip(),
        employee_status="pending" if employee_required else "not_required",
        institution_status="pending" if account_type == RegistrationAccountType.institution_user else "not_required",
        status="pending_email_verification",
    )
    document_path: Path | None = None
    if identity_image:
        image_bytes, content_type, extension = identity_image
        stored_name = f"identity-{uuid.uuid4().hex}.{extension}"
        document_path = Path(settings.upload_dir) / stored_name
        request.identity_document_stored_name = stored_name
        request.identity_document_sha256 = hashlib.sha256(image_bytes).hexdigest()
        request.identity_document_content_type = content_type
        request.identity_document_size = len(image_bytes)
        request.identity_document_uploaded_at = datetime.now(timezone.utc)
    db.add(request)
    db.flush()
    if employee_required:
        db.add(EmployeeVerification(
            registration_id=request.id,
            employee_id=request.employee_id or "",
            full_name=request.full_name,
            official_email=email,
            organization_name=request.organization_name,
            department=request.department,
            designation=request.designation,
            requested_role=account_type.value,
        ))
    token = issue_auth_token(db, "email_verification", registration_id=request.id)
    add_registration_audit(db, request, None, "registration_submitted", "", "Applicant submitted account request.")
    if identity_image:
        add_registration_audit(db, request, None, "identity_document_uploaded", request.status, "Applicant uploaded an ID card image for manual review.")
    try:
        if document_path and identity_image:
            document_path.write_bytes(identity_image[0])
        db.commit()
    except (OSError, SQLAlchemyError) as error:
        db.rollback()
        if document_path and document_path.is_file():
            document_path.unlink()
        raise HTTPException(status_code=500, detail="Registration could not be saved. Please try again.") from error
    try:
        delivered = send_account_email(
            email,
            "Verify your VaultTrace email",
            f"Hello {request.full_name},\n\nVerify your email address using this secure link:\n"
            f"{normalized_base_url(settings.email_verification_base_url or settings.frontend_base_url)}?verifyEmail={token}\n\n"
            "This confirms control of the email only. It does not verify identity, employment, institution affiliation, or role eligibility.\n",
        )
    except (OSError, smtplib.SMTPException):
        delivered = False
    return {
        "registration_id": request.public_id,
        "status": request.status,
        "email_delivery": "sent" if delivered else "unavailable",
        "message": "Check your email to continue." if delivered else "Email delivery is not configured or could not send. Contact your system administrator to enable verification email.",
    }


@app.post("/api/auth/register", status_code=201)
def register_account(data: RegistrationIn, db: Db):
    return create_registration(data, db)


@app.post("/api/auth/register-with-evidence", status_code=201)
def register_account_with_evidence(
    db: Db,
    registration_data: Annotated[str, Form()],
    identity_card: Annotated[UploadFile | None, File()] = None,
):
    try:
        data = RegistrationIn.model_validate_json(registration_data)
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="Registration details are invalid") from error
    identity_image = sanitize_identity_image(identity_card)
    return create_registration(data, db, identity_image)


@app.post("/api/auth/email/verify")
def verify_registration_email(data: OneTimeTokenIn, db: Db):
    now = datetime.now(timezone.utc)
    record = db.scalar(select(AuthTokenRecord).where(
        AuthTokenRecord.token_hash == token_digest(data.token),
        AuthTokenRecord.purpose == "email_verification",
    ).with_for_update())
    if not record or record.consumed_at or ensure_utc(record.expires_at) <= now or not record.registration_id:
        raise HTTPException(status_code=400, detail="This verification link is invalid, expired or already used")
    request = db.get(RegistrationRequest, record.registration_id)
    if not request or request.status == "rejected":
        raise HTTPException(status_code=400, detail="This registration cannot be verified")
    record.consumed_at = now
    previous = request.status
    request.email_verified_at = now
    update_registration_status(request)
    add_registration_audit(db, request, None, "email_verified", previous, "Applicant verified email ownership.")
    db.commit()
    return registration_status_payload(request)


@app.post("/api/auth/registration-status/{registration_id}")
def get_registration_status(registration_id: str, data: RegistrationStatusLookupIn, db: Db):
    email = normalized_email(data.email)
    request = db.scalar(select(RegistrationRequest).where(
        RegistrationRequest.public_id == registration_id,
        RegistrationRequest.email == email,
    ))
    if not request:
        raise HTTPException(status_code=404, detail="Registration request was not found")
    return registration_status_payload(request)


@app.post("/api/auth/registration-status/{registration_id}/resend")
def resend_registration_email(registration_id: str, data: RegistrationStatusLookupIn, db: Db):
    email = normalized_email(data.email)
    request = db.scalar(select(RegistrationRequest).where(
        RegistrationRequest.public_id == registration_id,
        RegistrationRequest.email == email,
    ))
    if not request:
        raise HTTPException(status_code=404, detail="Registration request was not found")
    if request.email_verified_at or request.status == "rejected":
        raise HTTPException(status_code=409, detail="This registration cannot resend email verification")
    now = datetime.now(timezone.utc)
    for token_record in db.scalars(select(AuthTokenRecord).where(
        AuthTokenRecord.registration_id == request.id,
        AuthTokenRecord.purpose == "email_verification",
        AuthTokenRecord.consumed_at.is_(None),
    )):
        token_record.consumed_at = now
    token = issue_auth_token(db, "email_verification", registration_id=request.id)
    db.commit()
    try:
        delivered = send_account_email(
            email,
            "Verify your VaultTrace email",
            f"Verify your email address using this secure link:\n"
            f"{normalized_base_url(settings.email_verification_base_url or settings.frontend_base_url)}?verifyEmail={token}\n\n"
            "This verifies email ownership only.",
        )
    except (OSError, smtplib.SMTPException):
        delivered = False
    if not delivered:
        raise HTTPException(status_code=503, detail="Email delivery is not configured or could not send. Contact your system administrator.")
    return {"message": "A new verification email was sent."}


@app.post("/api/auth/registration-status/{registration_id}/resubmit")
def resubmit_registration(
    registration_id: str,
    data: RegistrationResubmitIn,
    db: Db,
):
    email = normalized_email(data.email)
    request = db.scalar(select(RegistrationRequest).where(
        RegistrationRequest.public_id == registration_id,
        RegistrationRequest.email == email,
    ))
    if not request or request.status != "rejected":
        raise HTTPException(status_code=409, detail="This registration is not eligible for resubmission")
    institution = db.get(Institution, data.institution_id) if data.institution_id else None
    if data.institution_id and not institution:
        raise HTTPException(status_code=404, detail="Selected institution was not found")
    employee_required = RegistrationAccountType(request.account_type) not in {
        RegistrationAccountType.institution_user,
        RegistrationAccountType.viewer,
    }
    if RegistrationAccountType(request.account_type) == RegistrationAccountType.institution_user and not institution:
        raise HTTPException(status_code=422, detail="Select the institution you are requesting to join")
    if employee_required and (
        not data.employee_id
        or not data.organization_name.strip()
        or not data.department.strip()
        or not data.designation.strip()
    ):
        raise HTTPException(status_code=422, detail="Employee ID, organization, department and designation are required")
    if data.employee_id and data.employee_id.strip() != request.employee_id and db.scalar(
        select(EmployeeVerification.id).where(EmployeeVerification.employee_id == data.employee_id.strip())
    ):
        raise HTTPException(status_code=409, detail="That employee ID is already under verification")
    previous = request.status
    request.full_name = data.full_name.strip()
    request.organization_name = institution.name if institution else data.organization_name.strip()
    request.institution_id = institution.id if institution else None
    request.employee_id = data.employee_id.strip() if employee_required and data.employee_id else None
    request.department = data.department.strip()
    request.designation = data.designation.strip()
    request.email_verified_at = None
    request.identity_status = "pending"
    request.employee_status = "pending" if employee_required else "not_required"
    request.institution_status = "pending" if RegistrationAccountType(request.account_type) == RegistrationAccountType.institution_user else "not_required"
    request.role_status = "pending"
    request.decision_reason = ""
    request.decision_actor_id = None
    request.decision_at = None
    request.user_id = None
    update_registration_status(request)
    employee = db.scalar(select(EmployeeVerification).where(EmployeeVerification.registration_id == request.id))
    if employee_required:
        values = {
            "employee_id": request.employee_id or "",
            "full_name": request.full_name,
            "official_email": request.email,
            "organization_name": request.organization_name,
            "department": request.department,
            "designation": request.designation,
            "requested_role": request.account_type,
            "method": "manual_review",
            "status": "pending",
            "evidence_reference": "",
            "reviewer_id": None,
            "reviewed_at": None,
            "decision_reason": "",
        }
        if employee:
            for key, value in values.items():
                setattr(employee, key, value)
        else:
            db.add(EmployeeVerification(registration_id=request.id, **values))
    elif employee:
        db.delete(employee)
    now = datetime.now(timezone.utc)
    for token_record in db.scalars(select(AuthTokenRecord).where(
        AuthTokenRecord.registration_id == request.id,
        AuthTokenRecord.purpose == "email_verification",
        AuthTokenRecord.consumed_at.is_(None),
    )):
        token_record.consumed_at = now
    token = issue_auth_token(db, "email_verification", registration_id=request.id)
    add_registration_audit(db, request, None, "registration_resubmitted", previous, "Applicant resubmitted registration for review.")
    db.commit()
    try:
        delivered = send_account_email(
            email,
            "Verify your VaultTrace email",
            f"Your registration was resubmitted. Verify your email address using this secure link:\n"
            f"{normalized_base_url(settings.email_verification_base_url or settings.frontend_base_url)}?verifyEmail={token}\n",
        )
    except (OSError, smtplib.SMTPException):
        delivered = False
    return {
        "registration_id": request.public_id,
        "status": request.status,
        "email_delivery": "sent" if delivered else "unavailable",
        "message": "Check your email to continue." if delivered else "Email delivery is not configured or could not send. Contact your system administrator.",
    }


@app.post("/api/auth/password-reset/request", status_code=202)
def request_password_reset(data: PasswordResetRequestIn, db: Db):
    email = normalized_email(data.email)
    user = db.scalar(select(User).where(User.email == email, User.active.is_(True)))
    if user:
        token = issue_auth_token(db, "password_reset", user_id=user.id)
        db.commit()
        try:
            send_account_email(
                email,
                "VaultTrace password reset",
                f"Reset your VaultTrace password using this one-time link:\n"
                f"{normalized_base_url(settings.frontend_base_url)}?resetPassword={token}\n\n"
                "If you did not request this, ignore this email.",
            )
        except (OSError, smtplib.SMTPException):
            return {"message": "If an active account uses that email, password reset instructions will be sent."}
    return {"message": "If an active account uses that email, password reset instructions will be sent."}


@app.post("/api/auth/password-reset/confirm")
def confirm_password_reset(data: PasswordResetConfirmIn, db: Db):
    now = datetime.now(timezone.utc)
    record = db.scalar(select(AuthTokenRecord).where(
        AuthTokenRecord.token_hash == token_digest(data.token),
        AuthTokenRecord.purpose == "password_reset",
    ).with_for_update())
    if not record or record.consumed_at or ensure_utc(record.expires_at) <= now or not record.user_id:
        raise HTTPException(status_code=400, detail="This password reset token is invalid, expired or already used")
    user = db.get(User, record.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=400, detail="This password reset token is invalid, expired or already used")
    record.consumed_at = now
    user.password_hash = pwd_context.hash(data.password)
    db.add(AuditEvent(actor_id=user.id, action="password_reset", entity="user", entity_id=str(user.id), details="Password reset completed."))
    db.commit()
    return {"message": "Password reset complete. Sign in with your new password."}


@app.get("/api/auth/github/start", response_model=GitHubOAuthStartOut)
def start_github_verification(registration_id: str, db: Db):
    if not settings.github_client_id or not settings.github_client_secret or not settings.github_callback_url:
        raise HTTPException(status_code=503, detail="GitHub verification is unavailable because OAuth credentials are not configured")
    request = db.scalar(select(RegistrationRequest).where(RegistrationRequest.public_id == registration_id))
    if not request or request.status == "rejected":
        raise HTTPException(status_code=404, detail="An eligible registration request was not found")
    now = datetime.now(timezone.utc)
    for previous in db.scalars(select(GithubOAuthState).where(
        GithubOAuthState.registration_id == request.id,
        GithubOAuthState.consumed_at.is_(None),
    )):
        previous.consumed_at = now
    state = secrets.token_urlsafe(32)
    db.add(GithubOAuthState(
        registration_id=request.id,
        state_hash=token_digest(state),
        expires_at=now + timedelta(minutes=10),
    ))
    db.commit()
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": settings.github_callback_url,
        "scope": "read:user user:email",
        "state": state,
    }
    return {"authorization_url": "https://github.com/login/oauth/authorize?" + str(httpx.QueryParams(params))}


@app.get("/api/auth/github/callback")
def finish_github_verification(db: Db, code: str | None = None, state: str | None = None, error: str | None = None):
    if not state:
        raise HTTPException(status_code=400, detail="GitHub verification state is missing")
    now = datetime.now(timezone.utc)
    oauth_state = db.scalar(select(GithubOAuthState).where(GithubOAuthState.state_hash == token_digest(state)).with_for_update())
    if not oauth_state or oauth_state.consumed_at or ensure_utc(oauth_state.expires_at) <= now:
        raise HTTPException(status_code=400, detail="GitHub verification state is invalid, expired or already used")
    oauth_state.consumed_at = now
    db.commit()
    request = db.get(RegistrationRequest, oauth_state.registration_id)
    if error or not code:
        if not request:
            raise HTTPException(status_code=400, detail="Registration request was not found")
        return RedirectResponse(
            f"{normalized_base_url(settings.frontend_base_url)}?registrationId={request.public_id}&github=denied",
            status_code=303,
        )
    if not settings.github_client_id or not settings.github_client_secret or not settings.github_callback_url:
        raise HTTPException(status_code=503, detail="GitHub verification is not configured")
    try:
        with httpx.Client(timeout=10) as client:
            token_response = client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_callback_url,
                    "state": state,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get("access_token")
            if not access_token:
                raise HTTPException(status_code=400, detail="GitHub did not return an access token")
            profile_response = client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="GitHub verification could not be completed. Try again later.") from error
    provider_id = profile.get("id")
    if not provider_id:
        raise HTTPException(status_code=400, detail="GitHub did not return a valid account identity")
    if not request or request.status == "rejected":
        raise HTTPException(status_code=400, detail="Registration request is no longer eligible for verification")
    request.github_provider_id = str(provider_id)
    request.github_login = str(profile.get("login", ""))[:100]
    request.github_verified_at = now
    db.add(RegistrationAuditEvent(
        registration_id=request.id,
        actor_id=None,
        action="github_account_verified",
        previous_status=request.status,
        new_status=request.status,
        reason="GitHub account ownership checked; no identity or eligibility decision inferred.",
    ))
    db.commit()
    return RedirectResponse(
        f"{normalized_base_url(settings.frontend_base_url)}?registrationId={request.public_id}&github=verified",
        status_code=303,
    )


@app.get("/api/admin/registration-requests")
def list_registration_requests(
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))],
    status: str = "",
):
    query = select(RegistrationRequest)
    if status:
        query = query.where(RegistrationRequest.status == status)
    requests = db.scalars(query.order_by(RegistrationRequest.created_at.desc())).all()
    institution_names = {
        institution_id: name
        for institution_id, name in db.execute(
            select(Institution.id, Institution.name).where(
                Institution.id.in_({item.institution_id for item in requests if item.institution_id})
            )
        ).all()
    } if any(item.institution_id for item in requests) else {}
    return [{
        "id": request.id,
        "registration_id": request.public_id,
        "username": request.username,
        "full_name": request.full_name,
        "email": request.email,
        "account_type": request.account_type,
        "organization_name": request.organization_name,
        "institution_id": request.institution_id,
        "institution_name": institution_names.get(request.institution_id),
        "employee_id": request.employee_id,
        "department": request.department,
        "designation": request.designation,
        "status": request.status,
        "email_verified_at": request.email_verified_at,
        "identity_status": request.identity_status,
        "employee_status": request.employee_status,
        "institution_status": request.institution_status,
        "role_status": request.role_status,
        "github_login": request.github_login,
        "github_verified_at": request.github_verified_at,
        "created_at": request.created_at,
        "decision_reason": request.decision_reason,
        "decision_at": request.decision_at,
        "has_identity_document": request.identity_document_stored_name is not None,
        "identity_document_content_type": request.identity_document_content_type,
        "identity_document_size": request.identity_document_size,
    } for request in requests]


@app.get("/api/admin/registration-requests/{registration_id}/identity-document")
def view_registration_identity_document(
    registration_id: int,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))],
):
    registration = db.get(RegistrationRequest, registration_id)
    if not registration or not registration.identity_document_stored_name:
        raise HTTPException(status_code=404, detail="No ID card image is available for this registration")
    upload_root = Path(settings.upload_dir).resolve()
    document_path = (upload_root / registration.identity_document_stored_name).resolve()
    if upload_root not in document_path.parents or not document_path.is_file():
        raise HTTPException(status_code=404, detail="The ID card image could not be found")
    add_registration_audit(
        db,
        registration,
        user.id,
        "identity_document_viewed",
        registration.status,
        "Authorized reviewer viewed the private ID card image.",
    )
    db.commit()
    return Response(
        content=document_path.read_bytes(),
        media_type=registration.identity_document_content_type or "application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": "inline; filename=\"identity-card\"",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/admin/registration-requests/{registration_id}/decision")
def decide_registration(
    registration_id: int,
    data: RegistrationDecisionIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))],
):
    request = db.get(RegistrationRequest, registration_id)
    if not request:
        raise HTTPException(status_code=404, detail="Registration request was not found")
    if request.status in {"approved", "rejected"}:
        raise HTTPException(status_code=409, detail="This registration request is already closed")
    if data.action == "approve_role" and user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Only an administrator can approve requested account roles")

    now = datetime.now(timezone.utc)
    previous = request.status
    if data.action == "reject":
        request.status = "rejected"
        request.decision_reason = data.reason.strip()
        request.decision_actor_id = user.id
        request.decision_at = now
        if request.employee_id:
            employee = db.scalar(select(EmployeeVerification).where(EmployeeVerification.registration_id == request.id))
            if employee:
                employee.status = "rejected"
                employee.reviewer_id = user.id
                employee.reviewed_at = now
                employee.decision_reason = data.reason.strip()
    elif data.action == "verify_identity":
        if request.email_verified_at is None:
            raise HTTPException(status_code=409, detail="Email verification must be completed first")
        if request.identity_status != "pending":
            raise HTTPException(status_code=409, detail="Identity verification is not pending")
        request.identity_status = "approved"
        request.decision_reason = data.reason.strip()
        request.decision_actor_id = user.id
        request.decision_at = now
    elif data.action == "verify_employee":
        if not request.employee_id or request.employee_status != "pending":
            raise HTTPException(status_code=409, detail="Employee verification is not pending for this request")
        employee = db.scalar(select(EmployeeVerification).where(EmployeeVerification.registration_id == request.id))
        if not employee:
            raise HTTPException(status_code=409, detail="Employee verification record was not found")
        employee.status = "approved"
        employee.method = "authorized_manual_review"
        employee.evidence_reference = data.evidence_reference.strip()
        employee.reviewer_id = user.id
        employee.reviewed_at = now
        employee.decision_reason = data.reason.strip()
        request.employee_status = "approved"
        request.decision_reason = data.reason.strip()
        request.decision_actor_id = user.id
        request.decision_at = now
    elif data.action == "verify_institution":
        if not request.institution_id or request.institution_status != "pending":
            raise HTTPException(status_code=409, detail="Institution association is not pending for this request")
        request.institution_status = "approved"
        request.decision_reason = data.reason.strip()
        request.decision_actor_id = user.id
        request.decision_at = now
    elif data.action == "approve_role":
        if request.email_verified_at is None or request.identity_status != "approved":
            raise HTTPException(status_code=409, detail="Email and identity verification must be completed first")
        if request.employee_status not in {"approved", "not_required"}:
            raise HTTPException(status_code=409, detail="Employee verification must be completed first")
        if request.institution_status not in {"approved", "not_required"}:
            raise HTTPException(status_code=409, detail="Institution association must be approved first")
        requested_role = ACCOUNT_TYPE_ROLES[RegistrationAccountType(request.account_type)]
        if db.scalar(select(User.id).where(User.username == request.username)) or db.scalar(
            select(User.id).where(User.email == request.email)
        ):
            raise HTTPException(status_code=409, detail="Username or email is already assigned to an account")
        new_user = User(
            username=request.username,
            email=request.email,
            password_hash=request.password_hash,
            role=requested_role,
            active=True,
        )
        db.add(new_user)
        db.flush()
        if request.institution_id:
            db.add(UserInstitutionMembership(
                user_id=new_user.id,
                institution_id=request.institution_id,
            ))
        request.user_id = new_user.id
        request.role_status = "approved"
        request.decision_reason = data.reason.strip()
        request.decision_actor_id = user.id
        request.decision_at = now
    update_registration_status(request)
    add_registration_audit(db, request, user.id, data.action, previous, data.reason.strip())
    db.add(AuditEvent(
        actor_id=user.id,
        action=f"registration_{data.action}",
        entity="registration",
        entity_id=request.public_id,
        details=data.reason.strip(),
    ))
    db.commit()
    db.refresh(request)
    return registration_status_payload(request)


@app.get("/api/admin/users", response_model=list[AdminUserOut])
def list_users(db: Db, user: Annotated[User, Depends(require_roles(Role.admin))]):
    return db.scalars(select(User).order_by(User.id)).all()


@app.patch("/api/admin/users/{user_id}/activation", response_model=AdminUserOut)
def set_user_activation(
    user_id: int,
    data: UserActivationIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin))],
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User was not found")
    if target.id == user.id and not data.active:
        raise HTTPException(status_code=409, detail="Administrators cannot suspend their own active session")
    target.active = data.active
    db.add(AuditEvent(
        actor_id=user.id,
        action="user_activated" if data.active else "user_suspended",
        entity="user",
        entity_id=str(target.id),
        details=data.reason.strip(),
    ))
    db.commit()
    db.refresh(target)
    return target


@app.post("/api/institution-memberships")
def create_membership(
    data: MembershipIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin))],
):
    if not db.get(User, data.user_id):
        raise HTTPException(status_code=404, detail="User not found")
    if not db.get(Institution, data.institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    existing = db.scalar(
        select(UserInstitutionMembership).where(
            UserInstitutionMembership.user_id == data.user_id,
            UserInstitutionMembership.institution_id == data.institution_id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Membership already exists")
    item = UserInstitutionMembership(**data.model_dump())
    db.add(item)
    db.add(AuditEvent(actor_id=user.id, action="membership_created", entity="institution", entity_id=str(data.institution_id), details=str(data.user_id)))
    db.commit()
    db.refresh(item)
    return {"id": item.id, **data.model_dump()}


@app.post("/api/auth/bootstrap", response_model=UserOut)
def bootstrap(db: Db, x_bootstrap_token: Annotated[str | None, Header()] = None):
    if settings.bootstrap_token:
        if not x_bootstrap_token or not secrets.compare_digest(x_bootstrap_token, settings.bootstrap_token):
            raise HTTPException(status_code=403, detail="A valid bootstrap token is required")
        if not settings.initial_admin_password or len(settings.initial_admin_password) < 12:
            raise HTTPException(status_code=503, detail="Configure INITIAL_ADMIN_PASSWORD with at least 12 characters before bootstrapping")
        password = settings.initial_admin_password
    else:
        password = "ChangeMe123!"
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(status_code=409, detail="Bootstrap already completed")
    user = User(username="admin", password_hash=pwd_context.hash(password), role=Role.admin)
    db.add(user); db.commit(); db.refresh(user)
    return user


@app.get("/api/institutions", response_model=list[InstitutionOut])
def list_institutions(
    db: Db,
    user: Annotated[User, Depends(current_user)],
    q: str = "",
    state: str = "",
    district: str = "",
    institution_type: str = "",
    page: int = 1,
    page_size: int = 50,
):
    if page < 1:
        raise HTTPException(status_code=422, detail="page must be at least 1")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size must be between 1 and 100")
    query = select(Institution)
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Institution.id).where(UserInstitutionMembership.user_id == user.id)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            Institution.name.ilike(pattern)
            | Institution.code.ilike(pattern)
            | Institution.aicte_id.ilike(pattern)
            | Institution.other_id.ilike(pattern)
        )
    if state:
        query = query.where(Institution.state == state)
    if district:
        query = query.where(Institution.district == district)
    if institution_type:
        query = query.where(Institution.institution_type == institution_type)
    return db.scalars(query.order_by(Institution.name).offset((page - 1) * page_size).limit(page_size)).all()


@app.get("/api/institutions/{institution_id}/programmes", response_model=list[ProgrammeOut])
def list_institution_programmes(
    institution_id: int,
    db: Db,
    user: Annotated[User, Depends(current_user)],
):
    if not db.get(Institution, institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    require_institution_access(db, user, institution_id)
    return db.scalars(
        select(InstitutionProgramme)
        .where(InstitutionProgramme.institution_id == institution_id)
        .order_by(InstitutionProgramme.level, InstitutionProgramme.course)
    ).all()


@app.post("/api/institutions", response_model=InstitutionOut)
def create_institution(data: InstitutionIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))]):
    if db.scalar(select(Institution).where(Institution.code == data.code)):
        raise HTTPException(status_code=409, detail="Institution code already exists")
    item = Institution(**data.model_dump()); db.add(item); db.commit(); db.refresh(item)
    db.add(AuditEvent(actor_id=user.id, action="create", entity="institution", entity_id=str(item.id))); db.commit()
    return item


def parse_institution_csv(content: bytes) -> tuple[list[dict[str, str]], list[tuple[int, str, dict[str, str]]]]:
    try:
        rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    required = {"name", "code"}
    if not rows or not required.issubset(set(rows[0])):
        raise HTTPException(status_code=422, detail="CSV must contain name and code columns")
    valid: list[dict[str, str]] = []
    errors: list[tuple[int, str, dict[str, str]]] = []
    for row_number, row in enumerate(rows, start=2):
        if len(row.get("name", "").strip()) < 2:
            errors.append((row_number, "name is required", row))
        elif len(row.get("code", "").strip()) < 2:
            errors.append((row_number, "code is required", row))
        else:
            valid.append({key: value.strip() for key, value in row.items()})
    return valid, errors


@app.post("/api/institutions/import/preview")
def preview_institution_import(db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))], file: UploadFile = File(...)):
    if file.content_type not in {"text/csv", "application/csv", "text/plain"}:
        raise HTTPException(status_code=415, detail="Upload a CSV file")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File exceeds configured size limit")
    valid, errors = parse_institution_csv(content)
    seen: set[str] = set()
    for row in valid:
        code = row["code"]
        if code in seen or db.scalar(select(Institution).where(Institution.code == code)):
            errors.append((0, f"duplicate institution code: {code}", row))
        seen.add(code)
    job = ImportJob(filename=file.filename or "institutions.csv", status=ImportStatus.preview, row_count=len(valid) + len(errors), error_count=len(errors), valid_rows=json.dumps(valid), created_by=user.id)
    db.add(job); db.flush()
    for row_number, message, row in errors:
        db.add(ImportRowError(job_id=job.id, row_number=row_number, message=message, raw_data=json.dumps(row)))
    db.commit()
    return {"job_id": job.id, "valid_rows": valid, "errors": [{"row": n, "message": m, "data": r} for n, m, r in errors]}


@app.post("/api/institutions/import/{job_id}")
def import_institutions(job_id: int, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))]):
    job = db.get(ImportJob, job_id)
    if not job or job.status != ImportStatus.preview:
        raise HTTPException(status_code=404, detail="Preview import job not found")
    errors = db.scalars(select(ImportRowError).where(ImportRowError.job_id == job_id)).all()
    if errors:
        raise HTTPException(status_code=422, detail="Correct preview errors before importing")
    imported = 0
    for row in json.loads(job.valid_rows):
        if db.scalar(select(Institution).where(Institution.code == row["code"])):
            raise HTTPException(status_code=409, detail=f"Institution code already exists: {row['code']}")
        db.add(Institution(name=row["name"], code=row["code"], address=row.get("address", "")))
        imported += 1
    job.status = ImportStatus.imported
    db.add(AuditEvent(actor_id=user.id, action="institution_imported", entity="import_job", entity_id=str(job.id), details=str(imported)))
    db.commit()
    return {"job_id": job.id, "imported": imported, "status": job.status.value}


@app.get("/api/import-jobs")
def list_import_jobs(db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.viewer))]):
    return db.scalars(select(ImportJob).order_by(ImportJob.id.desc())).all()


@app.post("/api/policies")
def create_policy(data: PolicyIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin))]):
    if db.scalar(select(PolicyRule).where(PolicyRule.rule_id == data.rule_id)):
        raise HTTPException(status_code=409, detail="Policy rule ID already exists")
    item = PolicyRule(**data.model_dump(exclude={"required_documents"}), required_documents=json.dumps(data.required_documents), created_by=user.id)
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="policy_created", entity="policy", entity_id=data.rule_id)); db.commit(); db.refresh(item)
    return {"id": item.id, "rule_id": item.rule_id, "version": item.version, "active": item.active}


@app.get("/api/policies")
def list_policies(db: Db, user: Annotated[User, Depends(current_user)]):
    return db.scalars(select(PolicyRule).order_by(PolicyRule.rule_id, PolicyRule.version.desc())).all()


@app.patch("/api/policies/{policy_id}/status")
def update_policy_status(
    policy_id: int,
    data: PolicyStatusIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin))],
):
    policy = db.get(PolicyRule, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    now = datetime.now(timezone.utc)
    if data.active:
        effective = policy.effective_date.replace(tzinfo=timezone.utc) if policy.effective_date.tzinfo is None else policy.effective_date
        expiry = policy.expiry_date.replace(tzinfo=timezone.utc) if policy.expiry_date and policy.expiry_date.tzinfo is None else policy.expiry_date
        if effective and effective > now:
            raise HTTPException(status_code=422, detail="Cannot activate a policy before its effective date")
        if expiry and expiry <= now:
            raise HTTPException(status_code=422, detail="Cannot activate an expired policy")
        active_sibling = db.scalars(
            select(PolicyRule).where(
                PolicyRule.rule_id == policy.rule_id,
                PolicyRule.id != policy.id,
                PolicyRule.active.is_(True),
            )
        ).all()
        for sibling in active_sibling:
            sibling.active = False
    policy.active = data.active
    db.add(AuditEvent(
        actor_id=user.id,
        action="policy_activated" if data.active else "policy_deactivated",
        entity="policy",
        entity_id=str(policy.id),
        details=policy.rule_id,
    ))
    db.commit()
    db.refresh(policy)
    return {"id": policy.id, "rule_id": policy.rule_id, "version": policy.version, "active": policy.active}


@app.post("/api/assessments")
def create_assessment(data: AssessmentIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))]):
    if not db.get(Institution, data.institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    require_institution_access(db, user, data.institution_id)
    policy = db.get(PolicyRule, data.policy_rule_id) if data.policy_rule_id else None
    if data.policy_rule_id and not policy:
        raise HTTPException(status_code=404, detail="Policy rule not found")
    now = datetime.now(timezone.utc)
    effective = policy.effective_date.replace(tzinfo=timezone.utc) if policy and policy.effective_date.tzinfo is None else policy.effective_date if policy else None
    expiry = policy.expiry_date.replace(tzinfo=timezone.utc) if policy and policy.expiry_date and policy.expiry_date.tzinfo is None else policy.expiry_date if policy else None
    policy_current = policy and policy.active and effective <= now and (expiry is None or expiry > now)
    status_value = "configured" if policy_current and data.amount is not None and data.amount >= policy.amount_floor else "policy_required"
    item = DepositAssessment(institution_id=data.institution_id, policy_rule_id=data.policy_rule_id, amount=data.amount, status=status_value, notes=data.notes, created_by=user.id)
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="assessment_created", entity="assessment", entity_id="pending")); db.commit(); db.refresh(item)
    return {"id": item.id, "status": item.status, "amount": item.amount, "policy_rule_id": item.policy_rule_id}


@app.get("/api/institutions/{institution_id}/assessments")
def list_assessments(institution_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    if not db.get(Institution, institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    require_institution_access(db, user, institution_id)
    return db.scalars(select(DepositAssessment).where(DepositAssessment.institution_id == institution_id).order_by(DepositAssessment.id.desc())).all()


@app.get("/api/fdrs", response_model=list[FdrOut])
def list_fdrs(db: Db, user: Annotated[User, Depends(current_user)], q: str = ""):
    query = select(Fdr).where(Fdr.identifier.ilike(f"%{q}%"))
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Fdr.institution_id).where(UserInstitutionMembership.user_id == user.id)
    return db.scalars(query.order_by(Fdr.id.desc())).all()


@app.get("/api/dashboard/recent-uploads", response_model=list[RecentUploadOut])
def dashboard_recent_uploads(
    db: Db,
    user: Annotated[User, Depends(current_user)],
    limit: int = Query(default=5, ge=1, le=20),
):
    query = select(Document, Fdr).join(Fdr, Fdr.id == Document.fdr_id)
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(
            UserInstitutionMembership,
            UserInstitutionMembership.institution_id == Fdr.institution_id,
        ).where(UserInstitutionMembership.user_id == user.id)
    rows = db.execute(query.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit)).all()
    return [
        {
            "id": document.id,
            "fdr_id": fdr.id,
            "identifier": fdr.identifier,
            "original_name": document.original_name,
            "content_type": document.content_type,
            "size": document.size,
            "created_at": document.created_at,
            "status": fdr.status,
        }
        for document, fdr in rows
    ]


@app.get("/api/fdr-intakes", response_model=list[FdrIntakeOut])
def list_fdr_intakes(db: Db, user: Annotated[User, Depends(current_user)]):
    query = select(FdrIntake)
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(Fdr, Fdr.id == FdrIntake.source_fdr_id).join(
            UserInstitutionMembership,
            UserInstitutionMembership.institution_id == Fdr.institution_id,
        ).where(UserInstitutionMembership.user_id == user.id)
    intakes = db.scalars(query.order_by(FdrIntake.id.desc())).all()
    return [
        {
            "id": intake.id,
            "source_document_id": intake.source_document_id,
            "source_fdr_id": intake.source_fdr_id,
            "candidate_fields": json.loads(intake.candidate_fields),
            "status": intake.status,
            "created_at": intake.created_at,
        }
        for intake in intakes
    ]


@app.post("/api/fdr-intakes", response_model=FdrIntakeOut)
def create_fdr_intake(
    data: FdrIntakeIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))],
):
    document = db.get(Document, data.source_document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Source document not found")
    require_fdr_access(db, user, document.fdr_id)
    if not db.scalar(select(ExtractionResult).where(ExtractionResult.document_id == document.id)):
        raise HTTPException(status_code=409, detail="Run document extraction before submitting an intake")
    intake = FdrIntake(
        source_document_id=document.id,
        source_fdr_id=document.fdr_id,
        candidate_fields=json.dumps(data.fields.model_dump(exclude_none=True)),
        submitted_by=user.id,
    )
    db.add(intake)
    db.flush()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="submit_incomplete_intake",
            entity="fdr_intake",
            entity_id=str(intake.id),
            details=f"Source document {document.id}; pending completion",
        )
    )
    db.commit()
    db.refresh(intake)
    return {
        "id": intake.id,
        "source_document_id": intake.source_document_id,
        "source_fdr_id": intake.source_fdr_id,
        "candidate_fields": json.loads(intake.candidate_fields),
        "status": intake.status,
        "created_at": intake.created_at,
    }


@app.post("/api/fdrs", response_model=FdrOut)
def create_fdr(data: FdrIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.institution_user))]):
    if not db.get(Institution, data.institution_id):
        raise HTTPException(status_code=404, detail="Institution not found")
    require_institution_access(db, user, data.institution_id)
    if db.scalar(select(Fdr).where(Fdr.identifier == data.identifier)):
        raise HTTPException(status_code=409, detail="FDR identifier already exists")
    item = Fdr(**data.model_dump(), created_by=user.id); db.add(item); db.flush()
    db.add(InstrumentVersion(fdr_id=item.id, version_number=1, change_reason="Initial registration", snapshot=item.identifier, created_by=user.id))
    db.add(LifecycleEvent(fdr_id=item.id, from_status="", to_status=FdrStatus.draft.value, reason="Initial registration", actor_id=user.id))
    db.commit(); db.refresh(item)
    db.add(AuditEvent(actor_id=user.id, action="create", entity="fdr", entity_id=str(item.id))); db.commit()
    return item


@app.patch("/api/fdrs/{fdr_id}/status", response_model=FdrOut)
def change_status(fdr_id: int, data: StatusChange, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer))]):
    fdr = require_fdr_access(db, user, fdr_id)
    allowed = {FdrStatus.draft: {FdrStatus.submitted}, FdrStatus.submitted: {FdrStatus.under_review, FdrStatus.rejected}, FdrStatus.under_review: {FdrStatus.verified, FdrStatus.rejected}, FdrStatus.verified: {FdrStatus.release_requested}, FdrStatus.release_requested: {FdrStatus.approved, FdrStatus.rejected}, FdrStatus.approved: {FdrStatus.executed}, FdrStatus.executed: {FdrStatus.closed}}
    if data.status not in allowed.get(fdr.status, set()):
        raise HTTPException(status_code=422, detail=f"Invalid transition from {fdr.status.value} to {data.status.value}")
    if not can_change_status(user, fdr.status, data.status):
        raise HTTPException(status_code=403, detail="Role cannot perform this lifecycle transition")
    if data.status == FdrStatus.approved and fdr.created_by == user.id:
        raise HTTPException(status_code=403, detail="Separation of duties prevents self-approval")
    previous = fdr.status.value
    fdr.status = data.status
    db.add(LifecycleEvent(fdr_id=fdr.id, from_status=previous, to_status=data.status.value, actor_id=user.id))
    db.add(AuditEvent(actor_id=user.id, action="status_change", entity="fdr", entity_id=str(fdr.id), details=data.status.value)); db.commit(); db.refresh(fdr)
    return fdr


@app.post("/api/fdrs/{fdr_id}/documents")
def upload_document(fdr_id: int, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.institution_user))], file: UploadFile = File(...)):
    require_fdr_access(db, user, fdr_id)
    content_type = file.content_type
    if content_type == "image/jpg":
        content_type = "image/jpeg"
    if content_type not in {"application/pdf", "image/png", "image/jpeg"}: raise HTTPException(status_code=415, detail="Only PDF, PNG and JPEG files are accepted")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes: raise HTTPException(status_code=413, detail="File exceeds configured size limit")
    digest = hashlib.sha256(content).hexdigest()
    if db.scalar(select(Document).where(Document.sha256 == digest)): raise HTTPException(status_code=409, detail="Duplicate document hash")
    stored = f"{uuid.uuid4().hex}{Path(file.filename or 'upload').suffix.lower()}"
    Path(settings.upload_dir, stored).write_bytes(content)
    item = Document(fdr_id=fdr_id, original_name=file.filename or "upload", stored_name=stored, sha256=digest, content_type=content_type, size=len(content))
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="upload", entity="document", entity_id=stored)); db.commit()
    return {"id": item.id, "sha256": digest, "name": item.original_name}


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    require_fdr_access(db, user, document.fdr_id)
    path = (Path(settings.upload_dir) / document.stored_name).resolve()
    upload_root = Path(settings.upload_dir).resolve()
    if upload_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Document content is unavailable")
    return FileResponse(path, media_type=document.content_type, filename=document.original_name)


@app.get("/api/fdrs/{fdr_id}/documents", response_model=list[DocumentOut])
def list_documents(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    require_fdr_access(db, user, fdr_id)
    return db.scalars(select(Document).where(Document.fdr_id == fdr_id).order_by(Document.created_at)).all()


@app.post("/api/documents/{document_id}/extract")
def extract_document_text(
    document_id: int,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer))],
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    require_fdr_access(db, user, document.fdr_id)
    if document.content_type not in {"application/pdf", "image/png", "image/jpeg"}:
        raise HTTPException(status_code=415, detail="Local extraction supports PDF, PNG and JPEG documents only")
    path = (Path(settings.upload_dir) / document.stored_name).resolve()
    upload_root = Path(settings.upload_dir).resolve()
    if upload_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Document content is unavailable")
    tesseract_path = settings.tesseract_cmd or shutil.which("tesseract")
    if not tesseract_path:
        default_tesseract = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        if default_tesseract.is_file():
            tesseract_path = str(default_tesseract)
    if tesseract_path:
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    try:
        if document.content_type == "application/pdf":
            with fitz.open(path) as pdf:
                page_count = pdf.page_count
                embedded_text = "\n\n".join(page.get_text("text") for page in pdf).strip()
                if embedded_text:
                    text = embedded_text
                    provider = "local-pymupdf"
                else:
                    pages = []
                    for page in pdf:
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
                        pages.append(pytesseract.image_to_string(image))
                    text = "\n\n".join(pages).strip()
                    provider = "local-tesseract"
        else:
            with Image.open(path) as image:
                text = pytesseract.image_to_string(image).strip()
            page_count = 1
            provider = "local-tesseract"
    except pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Tesseract OCR is not installed or configured. Set TESSERACT_CMD to the executable path.",
        ) from exc
    except pytesseract.TesseractError as exc:
        raise HTTPException(status_code=422, detail="Tesseract could not process the document") from exc
    except (fitz.FileDataError, OSError) as exc:
        raise HTTPException(status_code=422, detail="Document could not be parsed") from exc
    result = ExtractionResult(
        document_id=document.id,
        provider=provider,
        status="completed",
        page_count=page_count,
        extracted_text=text,
        authenticity_confirmed=False,
        created_by=user.id,
    )
    db.add(result)
    db.add(AuditEvent(
        actor_id=user.id,
        action="document_extracted",
        entity="document",
        entity_id=str(document.id),
        details=f"provider={provider};pages={page_count}",
    ))
    db.commit()
    db.refresh(result)
    return {
        "id": result.id,
        "document_id": result.document_id,
        "provider": result.provider,
        "status": result.status,
        "page_count": result.page_count,
        "text": result.extracted_text,
        "authenticity_confirmed": result.authenticity_confirmed,
    }


def _extracted_label(text: str, labels: list[str]) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        for label in labels:
            match = re.match(rf"^{label}\s*(?::|#|-|\s{{2,}})\s*(.*)$", line, re.IGNORECASE)
            if match:
                return match.group(1).strip() or (lines[index + 1] if index + 1 < len(lines) else "")
    return ""


def _candidate_date(value: str) -> str:
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", value)
    if iso_match:
        return f"{int(iso_match.group(1)):04d}-{int(iso_match.group(2)):02d}-{int(iso_match.group(3)):02d}"
    match = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", value)
    if not match:
        return ""
    year = match.group(3) if len(match.group(3)) == 4 else f"20{match.group(3)}"
    return f"{year}-{int(match.group(2)):02d}-{int(match.group(1)):02d}"


def _openai_candidates(text: str) -> dict[str, str | None]:
    if not settings.openai_api_key:
        return {}
    prompt = (
        "Extract FDR/security-deposit fields from this OCR text. This may be an AICTE affidavit with "
        "a multi-line table. Read table cells in column order and ignore transaction/reference numbers "
        "unless they are explicitly the FDR number. Return JSON only with these keys: "
        "identifier, bank_name, branch_name, ifsc_code, amount, amount_in_words, issue_date, "
        "maturity_date, beneficiary, joint_holder, institution_name, approval_case_reference. "
        "Return dates as YYYY-MM-DD and amounts as digits without commas. Use null when absent. "
        "Do not copy values from any previously registered instrument and do not invent values.\n\n"
        + text[:30000]
    )
    try:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "You extract structured fields conservatively from documents."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError):
        return {}


def _affidavit_candidates(text: str) -> dict[str, str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    table_match = re.search(r"Details of\s+RPGF\s*/?\s*Joint FDR(.*)", text, re.IGNORECASE | re.DOTALL)
    table_text = table_match.group(1) if table_match else ""

    fdr_ids = re.findall(r"\b(?:[A-Z0-9]+-)*FDR-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", text, re.IGNORECASE)
    application = re.search(
        r"\bapplication\s+(?:no\.?\s*)?([A-Z0-9]+(?:-[A-Z0-9]+){2,})\s+dated\b",
        normalized,
        re.IGNORECASE,
    )
    institution_match = re.search(
        r"\bour Institution\s+(.+?)\s+vide application\b",
        normalized,
        re.IGNORECASE,
    )
    beneficiary = "AICTE/Board" if re.search(r"\bmade with AICTE\s*/\s*Board\b", normalized, re.IGNORECASE) else ""

    amount_match = re.search(
        r"(?:₹|Rs\.?\s*)?~?\s*(\d{1,3}(?:,\d{2,3})+|\d{5,})\b",
        table_text,
        re.IGNORECASE,
    )
    table_dates = re.findall(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", table_text)
    bank_name = ""
    bank_match = re.search(r"\bBank\b", table_text, re.IGNORECASE)
    if bank_match:
        preceding = table_text[max(0, bank_match.start() - 100):bank_match.start()]
        name_tokens = re.findall(r"[A-Za-z][A-Za-z&'.-]{2,}", preceding)
        name_tokens = [token for token in name_tokens if token.lower() not in {"details", "board", "institution", "made", "with"}]
        if name_tokens:
            bank_name = " ".join(name_tokens[-2:] + ["Bank"])

    return {
        "identifier": fdr_ids[-1] if fdr_ids else "",
        "institution_name": institution_match.group(1).strip(" .,-") if institution_match else "",
        "approval_case_reference": application.group(1).strip() if application else "",
        "bank_name": bank_name,
        "amount": amount_match.group(1).replace(",", "") if amount_match else "",
        "issue_date": _candidate_date(table_dates[0]) if table_dates else "",
        "maturity_date": _candidate_date(table_dates[1]) if len(table_dates) > 1 else "",
        "beneficiary": beneficiary,
        "joint_holder": institution_match.group(1).strip(" .,-") if institution_match else "",
    }


@app.post("/api/documents/{document_id}/convert-to-fdr-draft")
def convert_document_to_fdr_draft(
    document_id: int,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer))],
    fdr_id: int | None = None,
):
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    require_fdr_access(db, user, document.fdr_id)
    extraction = db.scalar(select(ExtractionResult).where(ExtractionResult.document_id == document_id).order_by(ExtractionResult.id.desc()))
    if not extraction:
        raise HTTPException(status_code=422, detail="Extract the document before converting it to an FDR draft")
    source_fdr = db.get(Fdr, fdr_id or document.fdr_id)
    if source_fdr:
        require_fdr_access(db, user, source_fdr.id)
    text = extraction.extracted_text or ""
    ai_fields = _openai_candidates(text)
    local_fields = _affidavit_candidates(text)
    identifier = str(local_fields["identifier"] or ai_fields.get("identifier") or _extracted_label(text, [r"FDR\s*(?:no|number|id)", r"FD\s*(?:no|number|id)", r"certificate\s*(?:no|number|id)"]))
    bank = str(local_fields["bank_name"] or ai_fields.get("bank_name") or _extracted_label(text, [r"bank", r"issuing bank", r"scheduled bank"]))
    branch = str(_extracted_label(text, [r"branch", r"branch name"]) or ai_fields.get("branch_name") or "")
    ifsc = str(_extracted_label(text, [r"IFSC", r"IFSC code"]) or ai_fields.get("ifsc_code") or "").upper()
    amount = re.sub(r"[^\d.]", "", str(local_fields["amount"] or ai_fields.get("amount") or _extracted_label(text, [r"amount", r"amount \(Rs\.\)", r"principal", r"deposit"])))
    amount_in_words = str(ai_fields.get("amount_in_words") or _extracted_label(text, [r"amount in words", r"rupees"]))
    issue_date = _candidate_date(str(local_fields["issue_date"] or ai_fields.get("issue_date") or _extracted_label(text, [r"date of issue", r"issue date"])))
    maturity_date = _candidate_date(str(local_fields["maturity_date"] or ai_fields.get("maturity_date") or _extracted_label(text, [r"date of maturity", r"maturity date"])))
    beneficiary = str(local_fields["beneficiary"] or ai_fields.get("beneficiary") or _extracted_label(text, [r"beneficiary", r"in favour of", r"in favor of"]))
    joint_holder = str(local_fields["joint_holder"] or ai_fields.get("joint_holder") or "")
    institution_name = str(local_fields["institution_name"] or ai_fields.get("institution_name") or "")
    approval_case_reference = str(local_fields["approval_case_reference"] or ai_fields.get("approval_case_reference") or "")

    institution_id = None
    if institution_name:
        normalized_name = re.sub(r"\s*\((?:demo|sample|test)\)\s*$", "", institution_name, flags=re.IGNORECASE)
        normalized_name = re.sub(r"[^a-z0-9]", "", normalized_name.lower())
        institutions = db.scalars(select(Institution)).all()
        match = next(
            (
                item for item in institutions
                if re.sub(
                    r"[^a-z0-9]",
                    "",
                    re.sub(r"\s*\((?:demo|sample|test)\)\s*$", "", item.name, flags=re.IGNORECASE).lower(),
                ) == normalized_name
            ),
            None,
        )
        if match:
            institution_id = match.id
    elif source_fdr:
        institution_id = source_fdr.institution_id
        institution_name = source_fdr.institution.name
    fields = {
        "identifier": identifier if re.search(r"(?:FDR|FD|CERTIFICATE).*\d", identifier, re.IGNORECASE) else None,
        "institution_id": str(institution_id) if institution_id else None,
        "institution_name": institution_name or None,
        "approval_case_reference": approval_case_reference or None,
        "bank_name": bank or None,
        "branch_name": branch or None,
        "ifsc_code": ifsc if re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc) else None,
        "amount": amount or None,
        "amount_in_words": amount_in_words or None,
        "issue_date": issue_date or None,
        "maturity_date": maturity_date or None,
        "beneficiary": beneficiary or None,
        "joint_holder": joint_holder or None,
    }
    db.add(AuditEvent(actor_id=user.id, action="document_converted_to_fdr_draft", entity="document", entity_id=str(document_id), details="structured candidate fields returned"))
    db.commit()
    return {"document_id": document_id, "source_fdr_id": source_fdr.id if source_fdr else None, "fields": fields}


@app.post("/api/fdrs/{fdr_id}/provenance")
def add_provenance(fdr_id: int, data: ProvenanceIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer))]):
    require_fdr_access(db, user, fdr_id)
    if data.level == ProvenanceLevel.independently_confirmed and user.role not in {Role.admin, Role.reviewer}:
        raise HTTPException(status_code=403, detail="Only reviewers can record independent confirmation")
    item = FieldProvenance(fdr_id=fdr_id, reviewer_id=user.id if data.level in {ProvenanceLevel.reviewed, ProvenanceLevel.independently_confirmed} else None, **data.model_dump())
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="provenance", entity="fdr", entity_id=str(fdr_id), details=data.level.value)); db.commit()
    return {"id": item.id, "level": item.level.value}


@app.get("/api/fdrs/{fdr_id}/discrepancies")
def list_discrepancies(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    require_fdr_access(db, user, fdr_id)
    return _discrepancy_payloads(db, fdr_id)


def _discrepancy_payload(
    item: Discrepancy,
    detail: DiscrepancyAnalysisDetail | None,
    events: list[DiscrepancyReviewEvent],
    available_document_ids: set[int],
):
    return {
        "id": item.id,
        "fdr_id": item.fdr_id,
        "rule_id": item.rule_id,
        "title": detail.title if detail else item.rule_id,
        "affected_field": detail.affected_field if detail else "",
        "severity": item.severity,
        "explanation": item.explanation,
        "expected_value": item.expected_value,
        "expected_source": detail.expected_source if detail else "",
        "observed_value": item.observed_value,
        "observed_source": detail.observed_source if detail else "",
        "evidence_reference": detail.evidence_reference if detail else "",
        "evidence_document_ids": [
            int(document_id)
            for document_id in re.findall(r"Document #(\d+)", detail.evidence_reference if detail else "")
            if int(document_id) in available_document_ids
        ],
        "recommended_action": detail.recommended_action if detail else "",
        "analysis_method": detail.analysis_method if detail else "manual",
        "status": item.status.value,
        "review_status": detail.review_status if detail else (
            "pending" if item.status == DiscrepancyStatus.open else item.status.value
        ),
        "resolution_notes": item.resolution_notes,
        "created_at": item.created_at,
        "history": [
            {
                "id": event.id,
                "actor_id": event.actor_id,
                "action": event.action,
                "reason": event.reason,
                "created_at": event.created_at,
            }
            for event in events
        ],
    }


def _discrepancy_payloads(db: Session, fdr_id: int):
    items = db.scalars(
        select(Discrepancy).where(Discrepancy.fdr_id == fdr_id).order_by(Discrepancy.id.desc())
    ).all()
    ids = [item.id for item in items]
    available_document_ids = set(db.scalars(select(Document.id).where(Document.fdr_id == fdr_id)).all())
    details = {
        detail.discrepancy_id: detail
        for detail in db.scalars(
            select(DiscrepancyAnalysisDetail).where(DiscrepancyAnalysisDetail.discrepancy_id.in_(ids))
        ).all()
    } if ids else {}
    events: dict[int, list[DiscrepancyReviewEvent]] = {}
    if ids:
        for event in db.scalars(
            select(DiscrepancyReviewEvent)
            .where(DiscrepancyReviewEvent.discrepancy_id.in_(ids))
            .order_by(DiscrepancyReviewEvent.created_at, DiscrepancyReviewEvent.id)
        ).all():
            events.setdefault(event.discrepancy_id, []).append(event)
    return [
        _discrepancy_payload(item, details.get(item.id), events.get(item.id, []), available_document_ids)
        for item in items
    ]


def _normalize_analysis_value(field: str, value: str) -> str:
    if field == "amount":
        numeric = re.sub(r"[^\d.]", "", value.replace(",", ""))
        try:
            return str(Decimal(numeric).normalize())
        except InvalidOperation:
            return numeric
    if field in {"issue_date", "maturity_date"}:
        return _candidate_date(value) or value.strip().casefold()
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _ocr_fields(text: str) -> dict[str, str]:
    candidates = _affidavit_candidates(text)
    labels = {
        "identifier": [r"FDR\s*(?:no\.?|number|id)", r"FD\s*(?:no\.?|number|id)", r"certificate\s*(?:no\.?|number|id)"],
        "holder_name": [r"holder\s*name", r"name\s*of\s*depositor", r"depositor\s*name"],
        "institution_name": [r"institution\s*name", r"name\s*of\s*institution"],
        "amount": [r"principal\s*amount", r"deposit\s*amount", r"amount"],
        "issue_date": [r"date\s*of\s*issue", r"issue\s*date"],
        "maturity_date": [r"date\s*of\s*maturity", r"maturity\s*date", r"due\s*date"],
        "beneficiary": [r"beneficiary", r"in\s*favour\s*of", r"in\s*favor\s*of"],
        "bank_name": [r"issuing\s*bank", r"bank\s*name", r"bank"],
    }
    fields = {}
    for field, field_labels in labels.items():
        value = _extracted_label(text, field_labels) or candidates.get(field, "")
        value = value.strip()
        if field == "amount":
            value = re.sub(r"[^\d,.]", "", value)
        elif field in {"issue_date", "maturity_date"}:
            value = _candidate_date(value)
        if value:
            fields[field] = value
    return fields


def _analyze_fdr_discrepancies(db: Session, fdr: Fdr) -> list[Discrepancy]:
    findings: list[Discrepancy] = []

    def record(
        rule: str,
        title: str,
        field: str,
        severity: str,
        explanation: str,
        expected: str = "",
        observed: str = "",
        expected_source: str = "",
        observed_source: str = "",
        evidence_reference: str = "",
        recommended_action: str = "",
    ) -> None:
        rule_id = f"AUTO:{rule}"
        item = db.scalar(
            select(Discrepancy).where(Discrepancy.fdr_id == fdr.id, Discrepancy.rule_id == rule_id)
        )
        if not item:
            item = Discrepancy(
                fdr_id=fdr.id,
                rule_id=rule_id,
                severity=severity,
                explanation=explanation,
                expected_value=expected,
                observed_value=observed,
            )
            db.add(item)
            db.flush()
        else:
            item.severity = severity
            item.explanation = explanation
            item.expected_value = expected
            item.observed_value = observed
        detail = db.get(DiscrepancyAnalysisDetail, item.id)
        if not detail:
            detail = DiscrepancyAnalysisDetail(discrepancy_id=item.id)
            db.add(detail)
        detail.title = title
        detail.affected_field = field
        detail.expected_source = expected_source
        detail.observed_source = observed_source
        detail.evidence_reference = evidence_reference
        detail.recommended_action = recommended_action
        detail.analysis_method = "rule_based"
        findings.append(item)

    stored_fields = [
        ("identifier", fdr.identifier, "FDR master record", "High"),
        ("holder_name", fdr.holder_name, "FDR master record", "High"),
        ("approval_case_reference", fdr.approval_case_reference or "", "FDR master record", "Medium"),
        ("amount", str(fdr.amount) if fdr.amount is not None else "", "FDR master record", "Critical"),
        ("amount_in_words", fdr.amount_in_words or "", "FDR master record", "Medium"),
        ("issue_date", fdr.issue_date.date().isoformat() if fdr.issue_date else "", "FDR master record", "Medium"),
        ("maturity_date", fdr.maturity_date.date().isoformat() if fdr.maturity_date else "", "FDR master record", "Medium"),
        ("bank_name", fdr.bank_name or "", "FDR master record", "Medium"),
        ("branch_name", fdr.branch_name or "", "FDR master record", "Medium"),
        ("ifsc_code", fdr.ifsc_code or "", "FDR master record", "Medium"),
        ("beneficiary", fdr.beneficiary or "", "FDR master record", "Medium"),
        ("joint_holder", fdr.joint_holder or "", "FDR master record", "Medium"),
        ("institution_name", fdr.institution.name if fdr.institution else "", "Institution directory", "High"),
    ]
    for field, value, source, severity in stored_fields:
        if not value.strip():
            record(
                f"MISSING_FIELD:{field}",
                f"Missing {field.replace('_', ' ')}",
                field,
                severity,
                f"The {field.replace('_', ' ')} is not present in the {source.lower()}.",
                observed="Missing",
                observed_source=source,
                recommended_action="Review the source instrument and complete this field if the evidence supports it.",
            )

    provenance_fields = {
        "identifier": (fdr.identifier, "FDR master record"),
        "holder_name": (fdr.holder_name, "FDR master record"),
        "amount": (str(fdr.amount), "FDR master record"),
        "issue_date": (fdr.issue_date.date().isoformat() if fdr.issue_date else "", "FDR master record"),
        "maturity_date": (fdr.maturity_date.date().isoformat() if fdr.maturity_date else "", "FDR master record"),
        "bank_name": (fdr.bank_name or "", "FDR master record"),
        "beneficiary": (fdr.beneficiary or "", "FDR master record"),
        "institution_name": (fdr.institution.name if fdr.institution else "", "Institution directory"),
    }
    provenance_records = db.scalars(
        select(FieldProvenance).where(FieldProvenance.fdr_id == fdr.id).order_by(FieldProvenance.id)
    ).all()
    for provenance in provenance_records:
        expected, expected_source = provenance_fields.get(provenance.field_name, ("", ""))
        if not expected or _normalize_analysis_value(provenance.field_name, expected) == _normalize_analysis_value(provenance.field_name, provenance.value):
            continue
        evidence = f"Document #{provenance.source_document_id}" if provenance.source_document_id else provenance.evidence_reference
        record(
            f"PROVENANCE_CONFLICT:{provenance.id}",
            f"Reviewed provenance conflicts for {provenance.field_name.replace('_', ' ')}",
            provenance.field_name,
            "High" if provenance.level == ProvenanceLevel.independently_confirmed else "Medium",
            "A stored provenance value differs from the current instrument or institution record.",
            expected=expected,
            observed=provenance.value,
            expected_source=expected_source,
            observed_source=f"Field provenance {provenance.level.value}",
            evidence_reference=evidence,
            recommended_action="Review the provenance source and reconcile the conflicting records before making a decision.",
        )

    if fdr.issue_date and fdr.maturity_date and fdr.maturity_date <= fdr.issue_date:
        record(
            "DATE_ORDER",
            "Inconsistent issue and maturity dates",
            "issue_date / maturity_date",
            "High",
            "The stored maturity date is not later than the stored issue date.",
            expected="Maturity date after issue date",
            observed=f"{fdr.issue_date.date().isoformat()} / {fdr.maturity_date.date().isoformat()}",
            expected_source="FDR date rule",
            observed_source="FDR master record",
            recommended_action="Check both dates against the original instrument before updating the record.",
        )

    duplicates = db.scalars(
        select(Fdr).where(func.lower(Fdr.identifier) == fdr.identifier.casefold(), Fdr.id != fdr.id)
    ).all()
    for duplicate in duplicates:
        record(
            f"DUPLICATE_IDENTIFIER:{duplicate.id}",
            "Duplicate instrument reference",
            "identifier",
            "High",
            f"The instrument reference matches another stored FDR record (#{duplicate.id}).",
            expected=f"Unique instrument reference",
            observed=fdr.identifier,
            expected_source="FDR registry",
            observed_source=f"FDR records #{fdr.id} and #{duplicate.id}",
            evidence_reference=f"Related FDR record #{duplicate.id}",
            recommended_action="Compare both records and confirm whether one is a duplicate or a separate instrument.",
        )

    documents = db.scalars(
        select(Document).where(Document.fdr_id == fdr.id).order_by(Document.id)
    ).all()
    if not documents:
        record(
            "MISSING_SUPPORTING_DOCUMENT",
            "No supporting document attached",
            "supporting_evidence",
            "Medium",
            "No document record is attached to this instrument, so document-based comparisons were unavailable.",
            observed="No attached documents",
            observed_source="VaultTrace document records",
            recommended_action="Request and attach the supporting instrument document for review.",
        )

    extraction_rows = db.scalars(
        select(ExtractionResult)
        .join(Document, ExtractionResult.document_id == Document.id)
        .where(Document.fdr_id == fdr.id)
        .order_by(ExtractionResult.document_id, ExtractionResult.id)
    ).all()
    latest_extractions: dict[int, ExtractionResult] = {}
    for extraction in extraction_rows:
        latest_extractions[extraction.document_id] = extraction

    ocr_values: dict[str, list[tuple[str, str, str]]] = {}
    for document in documents:
        evidence = f"Document #{document.id}: {document.original_name}; SHA-256 {document.sha256}"
        content_path = (Path(settings.upload_dir) / document.stored_name).resolve()
        upload_root = Path(settings.upload_dir).resolve()
        try:
            if upload_root not in content_path.parents or not content_path.is_file():
                raise OSError("Document content unavailable")
            actual_hash = hashlib.sha256(content_path.read_bytes()).hexdigest()
        except OSError:
            record(
                f"DOCUMENT_CONTENT_UNAVAILABLE:{document.id}",
                "Document content unavailable",
                "document_integrity",
                "High",
                "VaultTrace has a document record and stored fingerprint, but the document bytes could not be read for verification.",
                expected=document.sha256,
                observed="Unavailable",
                expected_source="Stored document fingerprint",
                observed_source=f"Document storage for document #{document.id}",
                evidence_reference=evidence,
                recommended_action="Restore or re-upload the document through the authorised evidence workflow, then review its fingerprint.",
            )
        else:
            if actual_hash != document.sha256:
                record(
                    f"DOCUMENT_HASH_MISMATCH:{document.id}",
                    "Document fingerprint mismatch",
                    "document_integrity",
                    "Critical",
                    "The document bytes do not match the SHA-256 fingerprint recorded at upload.",
                    expected=document.sha256,
                    observed=actual_hash,
                    expected_source="Stored document fingerprint",
                    observed_source=f"Current document bytes for document #{document.id}",
                    evidence_reference=evidence,
                    recommended_action="Quarantine this evidence for review and verify the original through an authorised process.",
                )
        extraction = latest_extractions.get(document.id)
        if not extraction or extraction.status != "completed":
            record(
                f"OCR_NOT_AVAILABLE:{document.id}",
                "Document has no completed text extraction",
                "extracted_fields",
                "Informational",
                "No completed OCR/text extraction is available for this attached document; no OCR field comparison was made.",
                observed=extraction.status if extraction else "No extraction record",
                expected_source="Completed document extraction",
                observed_source=f"Document #{document.id}",
                evidence_reference=evidence,
                recommended_action="Run the existing local document extraction workflow if this document needs field comparison.",
            )
            continue
        fields = _ocr_fields(extraction.extracted_text or "")
        source = f"OCR ({extraction.provider}) · document #{document.id}"
        comparisons = {
            "identifier": (fdr.identifier, "FDR master record"),
            "holder_name": (fdr.holder_name, "FDR master record"),
            "amount": (str(fdr.amount), "FDR master record"),
            "issue_date": (fdr.issue_date.date().isoformat() if fdr.issue_date else "", "FDR master record"),
            "maturity_date": (fdr.maturity_date.date().isoformat() if fdr.maturity_date else "", "FDR master record"),
            "bank_name": (fdr.bank_name or "", "FDR master record"),
            "beneficiary": (fdr.beneficiary or "", "FDR master record"),
            "institution_name": (fdr.institution.name if fdr.institution else "", "Institution directory"),
        }
        for field, observed in fields.items():
            expected, expected_source = comparisons[field]
            ocr_values.setdefault(field, []).append((observed, source, evidence))
            if not expected or _normalize_analysis_value(field, expected) == _normalize_analysis_value(field, observed):
                continue
            severity = "Critical" if field == "amount" else "High" if field in {"identifier", "holder_name", "institution_name"} else "Medium"
            record(
                f"OCR_MISMATCH:{field}:{document.id}",
                f"{field.replace('_', ' ').capitalize()} differs from the stored record",
                field,
                severity,
                f"The value extracted from the document differs from the value in the {expected_source.lower()}.",
                expected=expected,
                observed=observed,
                expected_source=expected_source,
                observed_source=source,
                evidence_reference=evidence,
                recommended_action="Compare the cited OCR value with the original document and correct the record only when supported.",
            )

    for field, values in ocr_values.items():
        if len(values) < 2:
            continue
        baseline, baseline_source, baseline_evidence = values[0]
        for observed, observed_source, observed_evidence in values[1:]:
            if _normalize_analysis_value(field, baseline) == _normalize_analysis_value(field, observed):
                continue
            record(
                f"OCR_CONFLICT:{field}:{baseline_source.rsplit('#', 1)[-1]}:{observed_source.rsplit('#', 1)[-1]}",
                f"Conflicting extracted {field.replace('_', ' ')} values",
                field,
                "High" if field in {"identifier", "amount", "institution_name"} else "Medium",
                "Two attached documents have different extracted values for the same field.",
                expected=baseline,
                observed=observed,
                expected_source=baseline_source,
                observed_source=observed_source,
                evidence_reference=f"{baseline_evidence}; {observed_evidence}",
                recommended_action="Review both cited documents and determine which value, if either, is supported.",
            )

    return findings


@app.post("/api/fdrs/{fdr_id}/discrepancies")
def create_discrepancy(fdr_id: int, data: DiscrepancyIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer))]):
    require_fdr_access(db, user, fdr_id)
    item = Discrepancy(fdr_id=fdr_id, **data.model_dump())
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="discrepancy_created", entity="fdr", entity_id=str(fdr_id), details=data.rule_id)); db.commit(); db.refresh(item)
    return item


@app.post("/api/fdrs/{fdr_id}/discrepancies/analyze")
def analyze_discrepancies(
    fdr_id: int,
    db: Db,
    user: Annotated[User, Depends(current_user)],
):
    fdr = require_fdr_access(db, user, fdr_id)
    _analyze_fdr_discrepancies(db, fdr)
    db.add(AuditEvent(
        actor_id=user.id,
        action="discrepancy_analysis",
        entity="fdr",
        entity_id=str(fdr_id),
        details="rule_based",
    ))
    db.commit()
    payloads = _discrepancy_payloads(db, fdr_id)
    return {
        "fdr_id": fdr_id,
        "analysis_method": "rule_based",
        "summary": {
            "findings": len(payloads),
            "open": sum(1 for finding in payloads if finding["status"] == "open" and finding["review_status"] != "dismissed"),
        },
        "findings": payloads,
    }


@app.post("/api/fdrs/{fdr_id}/discrepancies/chat")
def ask_discrepancy_assistant(
    fdr_id: int,
    data: DiscrepancyChatIn,
    db: Db,
    user: Annotated[User, Depends(current_user)],
):
    fdr = require_fdr_access(db, user, fdr_id)
    _analyze_fdr_discrepancies(db, fdr)
    findings = _discrepancy_payloads(db, fdr_id)
    question = data.question.strip()
    normalized_question = question.casefold()
    field_terms = {
        "amount": {"amount", "principal", "value", "sum"},
        "identifier": {"identifier", "reference", "number", "fdr"},
        "holder_name": {"holder", "depositor"},
        "institution_name": {"institution", "college", "name"},
        "issue_date": {"issue", "issued"},
        "maturity_date": {"maturity", "mature", "due"},
        "document_integrity": {"hash", "fingerprint", "integrity"},
        "supporting_evidence": {"document", "evidence", "ocr", "extracted"},
        "bank_name": {"bank"},
        "beneficiary": {"beneficiary"},
    }
    words = set(re.findall(r"[a-z0-9]+", normalized_question))
    selected_fields = {
        field for field, terms in field_terms.items() if words.intersection(terms)
    }
    if "date" in words:
        selected_fields.update({"issue_date", "maturity_date"})
    asks_summary = bool(words.intersection({"summary", "summarize", "overall", "findings", "discrepancies", "issues"}))

    matching = [
        finding for finding in findings
        if asks_summary or finding["affected_field"] in selected_fields
    ]
    if not matching and not selected_fields:
        matching = findings[:5]

    sources = [f"FDR master record #{fdr.id}"]
    response_lines: list[str] = []
    if selected_fields == {"amount"}:
        response_lines.append(f"The recorded principal is {fdr.amount:,.2f} in the FDR master record.")
    elif selected_fields.intersection({"identifier", "holder_name", "institution_name", "issue_date", "maturity_date", "bank_name", "beneficiary"}):
        stored_values = {
            "identifier": ("Instrument reference", fdr.identifier),
            "holder_name": ("Holder", fdr.holder_name),
            "institution_name": ("Institution", fdr.institution.name if fdr.institution else ""),
            "issue_date": ("Issue date", fdr.issue_date.date().isoformat() if fdr.issue_date else ""),
            "maturity_date": ("Maturity date", fdr.maturity_date.date().isoformat() if fdr.maturity_date else ""),
            "bank_name": ("Bank", fdr.bank_name or ""),
            "beneficiary": ("Beneficiary", fdr.beneficiary or ""),
        }
        for field in selected_fields:
            if field in stored_values and stored_values[field][1]:
                label, value = stored_values[field]
                response_lines.append(f"{label}: {value}.")

    if not matching:
        if findings:
            response_lines.append(
                "I found no field-specific discrepancy finding for that question. "
                "That does not confirm the field was checked or that its values match; review the cited records. "
                "It does not establish authenticity."
            )
        else:
            response_lines.append(
                "No discrepancies were detected in the records available for analysis. "
                "This does not establish the instrument’s authenticity."
            )
    else:
        response_lines.append("Here is what the available VaultTrace analysis shows:")
        for finding in matching[:5]:
            expected = finding["expected_value"] or "not available"
            observed = finding["observed_value"] or "not available"
            line = (
                f"Finding #{finding['id']} ({finding['severity']}): {finding['title']}. "
                f"{finding['explanation']} Expected: {expected}"
            )
            if finding["expected_source"]:
                line += f" ({finding['expected_source']})"
            line += f"; observed: {observed}"
            if finding["observed_source"]:
                line += f" ({finding['observed_source']})"
            line += "."
            if finding["recommended_action"]:
                line += f" Recommended action: {finding['recommended_action']}"
            response_lines.append(line)
            sources.append(f"Finding #{finding['id']}")
            sources.extend(
                source
                for source in (finding["expected_source"], finding["observed_source"])
                if source
            )
            sources.extend(
                f"Document #{document_id}"
                for document_id in finding["evidence_document_ids"]
            )
        if len(matching) > 5:
            response_lines.append(f"{len(matching) - 5} additional matching findings are shown in the findings list.")

    db.add(AuditEvent(
        actor_id=user.id,
        action="discrepancy_chat_question",
        entity="fdr",
        entity_id=str(fdr_id),
        details="rule_based",
    ))
    db.commit()
    return {
        "fdr_id": fdr_id,
        "analysis_method": "rule_based",
        "reply": "\n\n".join(response_lines),
        "sources": list(dict.fromkeys(sources)),
    }


@app.post("/api/discrepancies/{discrepancy_id}/review")
def review_discrepancy(
    discrepancy_id: int,
    data: DiscrepancyReviewIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))],
):
    item = db.get(Discrepancy, discrepancy_id)
    if not item:
        raise HTTPException(status_code=404, detail="Discrepancy not found")
    require_fdr_access(db, user, item.fdr_id)
    if item.status == DiscrepancyStatus.waived and user.role != Role.admin and data.action != DiscrepancyReviewAction.add_note:
        raise HTTPException(status_code=403, detail="Only administrators can reopen a waived discrepancy")
    detail = db.get(DiscrepancyAnalysisDetail, item.id)
    if not detail:
        detail = DiscrepancyAnalysisDetail(discrepancy_id=item.id)
        db.add(detail)
    review_status = {
        DiscrepancyReviewAction.mark_reviewed: "reviewed",
        DiscrepancyReviewAction.confirm: "confirmed",
        DiscrepancyReviewAction.dismiss: "dismissed",
        DiscrepancyReviewAction.request_evidence: "evidence_requested",
        DiscrepancyReviewAction.escalate: "escalated",
    }
    if data.action in review_status:
        detail.review_status = review_status[data.action]
    if data.action == DiscrepancyReviewAction.dismiss:
        item.status = DiscrepancyStatus.resolved
        item.resolved_by = user.id
    elif data.action != DiscrepancyReviewAction.add_note and item.status != DiscrepancyStatus.open:
        item.status = DiscrepancyStatus.open
        item.resolved_by = None
    item.resolution_notes = data.reason
    db.add(DiscrepancyReviewEvent(
        discrepancy_id=item.id,
        actor_id=user.id,
        action=data.action.value,
        reason=data.reason,
    ))
    db.add(AuditEvent(
        actor_id=user.id,
        action="discrepancy_review",
        entity="discrepancy",
        entity_id=str(item.id),
        details=data.action.value,
    ))
    db.commit()
    return next(finding for finding in _discrepancy_payloads(db, item.fdr_id) if finding["id"] == item.id)


@app.patch("/api/discrepancies/{discrepancy_id}")
def resolve_discrepancy(discrepancy_id: int, data: ResolutionIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))]):
    item = db.get(Discrepancy, discrepancy_id)
    if not item:
        raise HTTPException(status_code=404, detail="Discrepancy not found")
    if data.status == DiscrepancyStatus.waived and user.role != Role.admin:
        raise HTTPException(status_code=403, detail="Only administrators can waive discrepancies")
    require_fdr_access(db, user, item.fdr_id)
    item.status = data.status; item.resolution_notes = data.resolution_notes; item.resolved_by = user.id
    detail = db.get(DiscrepancyAnalysisDetail, item.id)
    if not detail:
        detail = DiscrepancyAnalysisDetail(discrepancy_id=item.id)
        db.add(detail)
    if data.status == DiscrepancyStatus.resolved:
        detail.review_status = "resolved"
    elif data.status == DiscrepancyStatus.waived:
        detail.review_status = "dismissed"
    db.add(DiscrepancyReviewEvent(
        discrepancy_id=item.id,
        actor_id=user.id,
        action="resolve" if data.status == DiscrepancyStatus.resolved else "waive",
        reason=data.resolution_notes,
    ))
    db.add(AuditEvent(actor_id=user.id, action="discrepancy_resolved", entity="discrepancy", entity_id=str(item.id), details=data.status.value)); db.commit()
    return next(
        finding for finding in _discrepancy_payloads(db, item.fdr_id) if finding["id"] == item.id
    )


@app.post("/api/fdrs/{fdr_id}/verification")
def update_verification(fdr_id: int, data: VerificationIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer, Role.verification_officer))]):
    fdr = require_fdr_access(db, user, fdr_id)
    if data.status in {VerificationStatus.verified, VerificationStatus.rejected} and len(data.evidence_reference.strip()) < 3:
        raise HTTPException(status_code=422, detail="Evidence reference is required for a terminal verification decision")
    case = db.scalar(select(VerificationCase).where(VerificationCase.fdr_id == fdr_id))
    if not case:
        case = VerificationCase(fdr_id=fdr_id)
        db.add(case)
    case.status = data.status; case.assigned_to = user.id; case.outcome_notes = data.outcome_notes; case.evidence_reference = data.evidence_reference
    if data.status == VerificationStatus.verified:
        fdr.status = FdrStatus.verified
    db.add(AuditEvent(actor_id=user.id, action="verification", entity="fdr", entity_id=str(fdr_id), details=data.status.value)); db.commit()
    return {"fdr_id": fdr_id, "status": case.status.value, "fdr_status": fdr.status.value}


@app.get("/api/fdrs/{fdr_id}/versions", response_model=list[InstrumentVersionOut])
def list_versions(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    require_fdr_access(db, user, fdr_id)
    return db.scalars(select(InstrumentVersion).where(InstrumentVersion.fdr_id == fdr_id).order_by(InstrumentVersion.version_number)).all()


@app.post("/api/fdrs/{fdr_id}/renewal-replacement")
def request_renewal_or_replacement(
    fdr_id: int,
    data: InstrumentChangeIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))],
):
    fdr = require_fdr_access(db, user, fdr_id)
    if fdr.status != FdrStatus.verified:
        raise HTTPException(status_code=422, detail="Only verified FDRs can enter renewal or replacement review")
    current_maturity = fdr.maturity_date.replace(tzinfo=timezone.utc) if fdr.maturity_date.tzinfo is None else fdr.maturity_date
    if data.proposed_maturity_date <= current_maturity:
        raise HTTPException(status_code=422, detail="Proposed maturity date must be after the current maturity date")
    if db.scalar(select(Fdr).where(Fdr.identifier == data.proposed_identifier)):
        raise HTTPException(status_code=409, detail="Proposed instrument identifier already exists")
    latest = db.scalar(
        select(InstrumentVersion)
        .where(InstrumentVersion.fdr_id == fdr_id)
        .order_by(InstrumentVersion.version_number.desc())
    )
    next_version = (latest.version_number if latest else 0) + 1
    snapshot = json.dumps({
        "change_type": data.change_type.value,
        "proposed_identifier": data.proposed_identifier,
        "proposed_maturity_date": data.proposed_maturity_date.isoformat(),
        "reason": data.reason,
        "source_identifier": fdr.identifier,
    })
    version = InstrumentVersion(
        fdr_id=fdr_id,
        version_number=next_version,
        source_version_id=latest.id if latest else None,
        change_reason=f"{data.change_type.value}: {data.reason}",
        snapshot=snapshot,
        created_by=user.id,
    )
    fdr.status = FdrStatus.draft
    db.add(version)
    db.add(LifecycleEvent(
        fdr_id=fdr_id,
        from_status=FdrStatus.verified.value,
        to_status=FdrStatus.draft.value,
        reason=f"{data.change_type.value} requested",
        actor_id=user.id,
    ))
    db.add(AuditEvent(
        actor_id=user.id,
        action=f"{data.change_type.value}_requested",
        entity="fdr",
        entity_id=str(fdr_id),
        details=data.proposed_identifier,
    ))
    db.commit()
    db.refresh(version)
    return {
        "id": version.id,
        "fdr_id": fdr_id,
        "version_number": version.version_number,
        "change_type": data.change_type.value,
        "status": fdr.status.value,
    }


@app.post("/api/fdrs/{fdr_id}/release-requests")
def request_release(fdr_id: int, data: ReleaseRequestIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.institution_user))]):
    fdr = require_fdr_access(db, user, fdr_id)
    if fdr.status != FdrStatus.verified:
        raise HTTPException(status_code=422, detail="FDR must be verified before release or refund request")
    if db.scalar(select(ReleaseRequest).where(ReleaseRequest.fdr_id == fdr_id, ReleaseRequest.status.in_([ "pending", "approved" ]))):
        raise HTTPException(status_code=409, detail="An active release request already exists")
    if db.scalar(select(Discrepancy).where(Discrepancy.fdr_id == fdr_id, Discrepancy.status == DiscrepancyStatus.open)):
        raise HTTPException(status_code=422, detail="Resolve open discrepancies before requesting release")
    item = ReleaseRequest(fdr_id=fdr_id, requested_by=user.id, **data.model_dump())
    fdr.status = FdrStatus.release_requested
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="release_requested", entity="fdr", entity_id=str(fdr_id))); db.commit(); db.refresh(item)
    return {"id": item.id, "status": item.status}


@app.patch("/api/release-requests/{request_id}/decision")
def decide_release(request_id: int, data: DecisionIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))]):
    item = db.get(ReleaseRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release request not found")
    require_fdr_access(db, user, item.fdr_id)
    if item.requested_by == user.id:
        raise HTTPException(status_code=403, detail="Separation of duties prevents self-approval")
    if item.status != "pending":
        raise HTTPException(status_code=422, detail="Release request is no longer pending")
    item.status = "approved" if data.approved else "rejected"; item.approved_by = user.id; item.decision_notes = data.decision_notes
    fdr = db.get(Fdr, item.fdr_id); fdr.status = FdrStatus.approved if data.approved else FdrStatus.rejected
    db.add(AuditEvent(actor_id=user.id, action="release_decision", entity="release_request", entity_id=str(item.id), details=item.status)); db.commit()
    return {"id": item.id, "status": item.status}


@app.get("/api/release-requests")
def list_release_requests(db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer, Role.auditor, Role.institution_user))]):
    query = select(ReleaseRequest).order_by(ReleaseRequest.id.desc())
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(Fdr, Fdr.id == ReleaseRequest.fdr_id).join(
            UserInstitutionMembership,
            UserInstitutionMembership.institution_id == Fdr.institution_id,
        ).where(UserInstitutionMembership.user_id == user.id)
    return db.scalars(query).all()


@app.post("/api/release-requests/{request_id}/execute")
def execute_release(request_id: int, data: ExecutionIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))]):
    item = db.get(ReleaseRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release request not found")
    require_fdr_access(db, user, item.fdr_id)
    if item.status != "approved":
        raise HTTPException(status_code=422, detail="Only approved requests can be executed")
    if item.requested_by == user.id or item.approved_by == user.id:
        raise HTTPException(status_code=403, detail="Execution must be performed by an independent operator")
    item.status = "executed"
    fdr = db.get(Fdr, item.fdr_id)
    fdr.status = FdrStatus.executed
    db.add(AuditEvent(actor_id=user.id, action="release_executed", entity="release_request", entity_id=str(item.id), details=data.evidence_reference))
    db.commit()
    return {"id": item.id, "status": item.status, "fdr_status": fdr.status.value}


@app.post("/api/release-requests/{request_id}/close")
def close_release(request_id: int, data: ExecutionIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.reviewer))]):
    item = db.get(ReleaseRequest, request_id)
    if not item:
        raise HTTPException(status_code=404, detail="Release request not found")
    require_fdr_access(db, user, item.fdr_id)
    if item.status != "executed":
        raise HTTPException(status_code=422, detail="Execution must be recorded before closure")
    execution_audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "release_executed",
            AuditEvent.entity == "release_request",
            AuditEvent.entity_id == str(item.id),
        ).order_by(AuditEvent.id.desc())
    )
    if execution_audit and execution_audit.actor_id == user.id:
        raise HTTPException(status_code=403, detail="Closure must be performed by an independent reviewer")
    item.status = "closed"
    fdr = db.get(Fdr, item.fdr_id)
    fdr.status = FdrStatus.closed
    db.add(AuditEvent(actor_id=user.id, action="release_closed", entity="release_request", entity_id=str(item.id), details=data.evidence_reference))
    db.commit()
    return {"id": item.id, "status": item.status, "fdr_status": fdr.status.value}


@app.get("/api/fdrs/{fdr_id}/timeline")
def lifecycle_timeline(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    require_fdr_access(db, user, fdr_id)
    return db.scalars(select(LifecycleEvent).where(LifecycleEvent.fdr_id == fdr_id).order_by(LifecycleEvent.created_at)).all()


@app.get("/api/fdrs/{fdr_id}/audit")
def instrument_audit(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    require_fdr_access(db, user, fdr_id)
    return db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity == "fdr", AuditEvent.entity_id == str(fdr_id))
        .order_by(AuditEvent.created_at.desc())
    ).all()


@app.get("/api/fdrs/{fdr_id}/release-requests")
def instrument_release_requests(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    require_fdr_access(db, user, fdr_id)
    return db.scalars(select(ReleaseRequest).where(ReleaseRequest.fdr_id == fdr_id).order_by(ReleaseRequest.created_at.desc())).all()


@app.post("/api/fdrs/{fdr_id}/custody")
def add_custody_event(fdr_id: int, data: CustodyIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.custody))]):
    require_fdr_access(db, user, fdr_id)
    item = CustodyEvent(fdr_id=fdr_id, actor_id=user.id, **data.model_dump())
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="custody_event", entity="fdr", entity_id=str(fdr_id), details=data.event_type)); db.commit(); db.refresh(item)
    return item


@app.get("/api/fdrs/{fdr_id}/custody")
def list_custody_events(fdr_id: int, db: Db, user: Annotated[User, Depends(current_user)]):
    return db.scalars(select(CustodyEvent).where(CustodyEvent.fdr_id == fdr_id).order_by(CustodyEvent.created_at.desc())).all()


@app.get("/api/maturity")
def maturity_calendar(db: Db, user: Annotated[User, Depends(current_user)], days: int = 90):
    horizon = datetime.now(timezone.utc) + timedelta(days=max(1, min(days, 730)))
    query = select(Fdr, Institution.name).join(Institution, Institution.id == Fdr.institution_id).where(Fdr.maturity_date <= horizon, Fdr.status.not_in([FdrStatus.closed, FdrStatus.rejected]))
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Fdr.institution_id).where(UserInstitutionMembership.user_id == user.id)
    rows = db.execute(query.order_by(Fdr.maturity_date)).all()
    return [{"id": row.id, "identifier": row.identifier, "institution_id": row.institution_id, "institution_name": institution_name, "maturity_date": row.maturity_date, "status": row.status.value, "days_remaining": ((row.maturity_date.replace(tzinfo=timezone.utc) if row.maturity_date.tzinfo is None else row.maturity_date) - datetime.now(timezone.utc)).days} for row, institution_name in rows]


@app.post("/api/fdrs/{fdr_id}/notifications")
def schedule_notification(fdr_id: int, data: NotificationIn, db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))]):
    require_fdr_access(db, user, fdr_id)
    item = NotificationEvent(fdr_id=fdr_id, **data.model_dump())
    db.add(item); db.add(AuditEvent(actor_id=user.id, action="notification_scheduled", entity="fdr", entity_id=str(fdr_id), details=data.channel)); db.commit(); db.refresh(item)
    return item


@app.patch("/api/notifications/{notification_id}/status")
def update_notification_status(
    notification_id: int,
    data: NotificationStatusIn,
    db: Db,
    user: Annotated[User, Depends(require_roles(Role.admin, Role.officer))],
):
    item = db.get(NotificationEvent, notification_id)
    if not item:
        raise HTTPException(status_code=404, detail="Notification not found")
    require_fdr_access(db, user, item.fdr_id)
    if item.status != "planned":
        raise HTTPException(status_code=422, detail="Only planned notifications can be marked unavailable")
    item.status = data.status
    db.add(AuditEvent(
        actor_id=user.id,
        action="notification_unavailable",
        entity="notification",
        entity_id=str(item.id),
        details=data.reason,
    ))
    db.commit()
    db.refresh(item)
    return {"id": item.id, "status": item.status, "reason": data.reason}


@app.get("/api/notifications")
def list_notifications(db: Db, user: Annotated[User, Depends(current_user)]):
    query = select(NotificationEvent).order_by(NotificationEvent.id.desc())
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(Fdr, Fdr.id == NotificationEvent.fdr_id).join(
            UserInstitutionMembership,
            UserInstitutionMembership.institution_id == Fdr.institution_id,
        ).where(UserInstitutionMembership.user_id == user.id)
    return db.scalars(query).all()


@app.get("/api/audit")
def audit_explorer(db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.auditor))], entity: str = "", action: str = ""):
    query = select(AuditEvent).order_by(AuditEvent.id.desc())
    if entity:
        query = query.where(AuditEvent.entity == entity)
    if action:
        query = query.where(AuditEvent.action == action)
    return db.scalars(query.limit(500)).all()


@app.get("/api/reports/instruments.csv")
def instrument_report(db: Db, user: Annotated[User, Depends(require_roles(Role.admin, Role.officer, Role.reviewer, Role.auditor))]):
    query = select(Fdr).order_by(Fdr.id)
    if user.role not in {Role.admin, Role.auditor}:
        query = query.join(
            UserInstitutionMembership,
            UserInstitutionMembership.institution_id == Fdr.institution_id,
        ).where(UserInstitutionMembership.user_id == user.id)
    rows = db.scalars(query).all()
    db.add(AuditEvent(
        actor_id=user.id,
        action="instrument_exported",
        entity="report",
        entity_id="instruments.csv",
        details=f"rows={len(rows)}",
    ))
    db.commit()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["identifier", "institution_id", "holder_name", "amount", "maturity_date", "status"])
    for row in rows:
        writer.writerow([row.identifier, row.institution_id, row.holder_name, row.amount, row.maturity_date.isoformat(), row.status.value])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=vaulttrace-instruments.csv"})


@app.get("/api/dashboard/summary")
def dashboard(db: Db, user: Annotated[User, Depends(current_user)]):
    if user.role in {Role.admin, Role.auditor}:
        institution_query = select(func.count(Institution.id))
        fdr_query = select(func.count(Fdr.id))
        verified_query = select(func.count(Fdr.id)).where(Fdr.status == FdrStatus.verified)
        pending_query = select(func.count(Fdr.id)).where(Fdr.status.in_([FdrStatus.submitted, FdrStatus.under_review]))
    else:
        institution_query = select(func.count(Institution.id)).join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Institution.id).where(UserInstitutionMembership.user_id == user.id)
        fdr_query = select(func.count(Fdr.id)).join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Fdr.institution_id).where(UserInstitutionMembership.user_id == user.id)
        verified_query = select(func.count(Fdr.id)).join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Fdr.institution_id).where(UserInstitutionMembership.user_id == user.id, Fdr.status == FdrStatus.verified)
        pending_query = select(func.count(Fdr.id)).join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Fdr.institution_id).where(UserInstitutionMembership.user_id == user.id, Fdr.status.in_([FdrStatus.submitted, FdrStatus.under_review]))
    return {"institutions": db.scalar(institution_query) or 0, "fdrs": db.scalar(fdr_query) or 0, "verified": db.scalar(verified_query) or 0, "pending": db.scalar(pending_query) or 0}


@app.get("/api/institutions/summary")
def institution_summary(db: Db, user: Annotated[User, Depends(current_user)]):
    institution_ids = select(Institution.id)
    if user.role not in {Role.admin, Role.auditor}:
        institution_ids = institution_ids.join(UserInstitutionMembership, UserInstitutionMembership.institution_id == Institution.id).where(UserInstitutionMembership.user_id == user.id)
    states = db.scalars(
        select(Institution.state).where(Institution.id.in_(institution_ids), Institution.state != "")
        .distinct()
        .order_by(Institution.state)
    ).all()
    types = db.scalars(
        select(Institution.institution_type).where(Institution.id.in_(institution_ids), Institution.institution_type != "")
        .distinct()
        .order_by(Institution.institution_type)
    ).all()
    return {
        "institutions": db.scalar(select(func.count(Institution.id)).where(Institution.id.in_(institution_ids))) or 0,
        "programmes": db.scalar(select(func.count(InstitutionProgramme.id)).where(InstitutionProgramme.institution_id.in_(institution_ids))) or 0,
        "states": states,
        "institution_types": types,
    }
