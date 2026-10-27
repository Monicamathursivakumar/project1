# VaultTrace

VaultTrace is a registry and controlled workflow for institutions, fixed deposit receipts (FDRs), evidence and release approvals. It is not an official government portal.

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
