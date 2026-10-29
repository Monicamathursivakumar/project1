# VaultTrace

VaultTrace is a registry and controlled workflow for institutions, fixed deposit receipts (FDRs), evidence and release approvals. It is not an official government portal.

The public home page introduces VaultTrace's record, verification and approval
workflows. Visitors can sign in or request an account; protected application
views continue to use the existing authentication and role checks.

## Local startup

### Backend (SQLite)

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Optional structured extraction with OpenAI:

```env
OPENAI_API_KEY=replace-with-a-local-key
OPENAI_MODEL=gpt-4o-mini
```

The FDR conversion endpoint uses OpenAI for conservative field extraction when configured and falls back to local label parsing when the key is absent or the provider is unavailable. Uploaded document text is sent to OpenAI only when `OPENAI_API_KEY` is configured.

An extracted FDR can be submitted as an incomplete intake draft without filling fields the source document does not contain. These drafts retain only the submitted candidates and source-document link; they remain pending completion and are not registered or verified FDR records.

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. On a fresh database, bootstrap the administrator once:

```powershell
curl.exe -X POST http://localhost:8000/api/auth/bootstrap
```

The initial development login is `admin` / `ChangeMe123!`; change it before any non-local use.

## Registration, verification and roles

Public registration creates a pending request, never an active login. Email
ownership, identity review, employee/institution verification and requested
role approval remain independent states. Identity and employee checks use
authorized manual review until an approved directory or identity provider is
configured. GitHub OAuth is optional and verifies GitHub account ownership
only; it does not establish identity, employment or eligibility. Configure
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` and
`SMTP_FROM_EMAIL` to deliver verification and password-reset email. Without
SMTP, the app clearly leaves requests pending and does not expose tokens.

Applicants of every requested role can optionally attach an institution or
employee ID card image in the registration wizard. JPEG and PNG files up to
5 MB are validated and re-encoded to remove image metadata before being stored
in the private upload directory. Only administrators and reviewing officers
can view the image through the authenticated review API; each view is audited.
The image is supporting material for manual review only and does not itself
verify identity or employment. Do not upload Aadhaar or other unnecessary
government ID documents.

The first administrator reviews requests at the **Account approvals** page.
Only an administrator can approve a requested role or suspend a user.
Department and institution membership is applied only after role approval;
institution-user access is scoped to the approved membership.

GitHub OAuth requires `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and
`GITHUB_CALLBACK_URL`. Set the callback to
`https://<api-service-host>/api/auth/github/callback` and register that exact
URL with GitHub. Leaving these unset makes GitHub verification unavailable.
The OAuth state is single-use, hashed at rest and expires after ten minutes.

Apply database changes to an existing installation with:

```powershell
cd backend
alembic upgrade head
```

The registration schema migration is `0010_registration_identity`; private
registration ID-card evidence is added by `0011_registration_identity_documents`.
Back up your database before applying migrations. A fresh database creates the
current schema on first startup.

The Render API container runs `alembic upgrade head` before starting FastAPI.
The migration chain is safe for the application's existing `create_all` schema
and applies the registration changes without resetting stored records.
Registration API routes include `/api/auth/register`,
`/api/auth/register-with-evidence`, `/api/auth/email/verify`,
`/api/auth/registration-status/{registration_id}`, password reset routes,
GitHub OAuth start/callback routes, and administrator review routes under
`/api/admin/registration-requests`; authorized reviewers view private ID images
at `/api/admin/registration-requests/{registration_id}/identity-document`.
The reviewer queue separates email, identity, employee,
institution-association and requested-role decisions.

### Local department demo accounts

For local demonstrations only, choose a shared password of at least 12
characters and set `DEMO_ACCOUNT_PASSWORD`, then run:

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
$env:ENABLE_DEMO_ACCOUNTS = "true"
python -m app.seed_demo_accounts
```

The command refuses to run when `APP_ENVIRONMENT=production` or on Render. It
creates `demo_institution_user`, `demo_reviewing_officer`,
`demo_verification_officer`, `demo_custody_officer`,
`demo_policy_administrator`, `demo_auditor` and `demo_viewer`; use the
`DEMO_ACCOUNT_PASSWORD` value to sign in. The existing bootstrapped admin is
not reset or duplicated. Demo staff are associated with the first institution
in the local catalogue; institution-user records are scoped to that college.

## Deploy a free shared Render demo

The root `render.yaml` Blueprint defines a Vite static site, Docker-based FastAPI
service and Render Postgres database using free plans. The frontend API URL and
browser CORS origin are linked to the deployed service URLs.

When the API starts, `PUBLIC_DEMO_MODE` creates synthetic institutions,
role-specific FDR workflows and public demo accounts in an empty demo database.
The frontend displays role sign-in cards. Authenticated users can use the
workflows allowed by their role; institution-user operations remain scoped to
their approved institution membership. The demo credentials are public by
design: `VaultTrace-Demo-2026!`. Changes are shared with other visitors. Do not
reuse this deployment or password for real records or production.

This is a writable temporary demo, not production:

- Free web services spin down after 15 minutes without traffic and can take
  about a minute to start again.
- The free database has a 1 GB limit, expires 30 days after creation, and has
  no backups. Render deletes it after the 14-day post-expiration grace period.
- Uploads go to the API's ephemeral filesystem and are lost on service restart,
  spin-down or redeploy. Do not upload real or sensitive documents.
- Uploaded files may disappear while their database metadata remains, so an
  older document can be listed but unavailable to download or reprocess.
- Seeded records are synthetic, but visitors can create and change shared
  records. Use synthetic data only.
- Public account registration and password reset are not offered in the hosted
  demo because no email-delivery provider is configured. Sign in with one of
  the shared role accounts; normal API authentication, role checks and
  institution scoping remain enabled.
- The API validates the initial database before seeding, then records a durable
  initialization marker so later starts accept shared records created through
  the demo and continue seeding idempotently.

To deploy:

1. Push the repository to a Git provider connected to Render. Do not commit
   `backend/.env`, local databases, secrets or uploaded files.
2. In Render, choose **New → Blueprint**, select the repository, review the
   free resources in `render.yaml`, and create the Blueprint.
3. Render generates the API `SECRET_KEY`. Do not expose it.
4. Open the frontend service URL and sign in using one of the role cards and the
   displayed shared demo password. Sample records are seeded automatically on
   the first API startup and repaired idempotently after restarts.
   The admin dashboard seeds at least 3,000 synthetic institutions, 438
   synthetic FDR records, eight records with a demo verified status, and two
   records needing attention; these are sample workflow statuses, not real bank
   confirmations.

For production, do not use the free plan. Upgrade the API and Postgres to paid
plans, attach persistent upload storage or use private object storage, configure
backups and an email provider, and review the security and privacy setup before
handling real documents. Local files in `backend/private_uploads` and the
SQLite development database are not uploaded to Render.

### Load the AICTE institution catalogue

The supplied `all-institutions-with-programmes.json` dataset can be loaded into the
SQLite database after the backend dependencies are installed:

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
python -m app.seed_institutions ..\all-institutions-with-programmes.json
```

The importer is idempotent. It stores institution metadata and every nested
programme in `institution_programmes`. Programme records are available through
`GET /api/institutions/{institution_id}/programmes`; institution searches also
support `state`, `district`, and `institution_type` filters.

To populate the workspace with linked demonstration scenarios for the registry,
verification, discrepancies, release, custody, maturity, notifications and audit
pages, run:

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
python -m app.seed_scenarios
```

The scenario loader is idempotent and clearly prefixes demo instruments with
`DEMO-FDR-`. It also creates a private evidence-vault document from the supplied
AICTE handbook when available.

To add clearly labeled sample maturities across the current and upcoming months and colleges
without changing existing FDRs, run:

```powershell
cd backend
$env:PYTHONPATH = (Get-Location).Path
python -m app.seed_scenarios --maturity-calendar-only
```

These draft, submitted, and under-review examples use the `DEMO-MATURITY-`
prefix and are excluded from verified instruments. The calendar seeder is
idempotent.

## PostgreSQL

`docker compose up --build` starts PostgreSQL and the backend. Set `DATABASE_URL` and `SECRET_KEY` through the environment for deployments. Uploaded files are private and stored outside the static frontend.

## Validation

```powershell
cd backend
pytest
cd ..\frontend
npm run build
```

## Scope and remaining external dependencies

The current prototype provides database-backed authentication, role checks, institution/FDR creation and search, detailed FDR registration (approval case, bank/branch/IFSC, dates, beneficiaries and lien declaration), CSV preview validation, policy records, deposit assessments, explicit FDR transitions, private document upload/retrieval with type/size/hash validation, local PDF text extraction with PyMuPDF, Tesseract OCR for scanned PDFs and PNG/JPEG evidence, audit events, dashboard aggregates, instrument version records, field provenance, discrepancies, verification, release/refund request controls, Alembic scaffolding and responsive shell. Production object storage, email/SMS delivery, an authorized bank confirmation API, and a production secrets manager remain deployment-specific dependencies. Extraction is never treated as authenticity proof.

The frontend now includes a responsive operations console with real routed views for the overview dashboard, institution directory, FDR registry, verification centre, evidence vault, discrepancy centre, release/refund requests and policy configuration. PDF and image uploads automatically invoke the configured extraction provider and report page/text metadata while preserving the explicit unconfirmed-authenticity state. All create and upload actions shown in these views call the backend APIs and persist state.

### Tesseract OCR

Install the Tesseract executable separately and set `TESSERACT_CMD` when it is not on `PATH` (for example, `C:\Program Files\Tesseract-OCR\tesseract.exe` on Windows). The backend uses PyMuPDF for PDFs that contain embedded text and automatically falls back to Tesseract for scanned/image-only PDFs. PNG and JPEG evidence is processed with Tesseract directly. If Tesseract is unavailable, the extraction endpoint returns `503` rather than claiming OCR completed.
