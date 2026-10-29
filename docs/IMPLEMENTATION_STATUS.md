# VaultTrace implementation status

## Completed foundation

- FastAPI service with SQLAlchemy models and configurable SQLite/PostgreSQL connection.
- Alembic initial migration scaffold.
- JWT authentication, bootstrap administrator and backend-enforced roles.
- Institution and FDR registry APIs with duplicate validation and explicit lifecycle transitions.
- Private document upload with MIME allow-list, size limit, SHA-256 persistence and duplicate hash rejection.
- Instrument version records, field-level provenance, persisted discrepancies, verification cases and controlled release/refund requests.
- Verification cases open the selected FDR in the discrepancy centre; rule-based findings compare stored fields, extracted text, document fingerprints and provenance, and retain source references and reviewer decision history.
- Policy rule records, policy-aware deposit assessment records, CSV import preview/error history, and permission-checked private document retrieval.
- Append-only audit event records for core mutations.
- Dashboard aggregates queried from the database.
- React/TypeScript responsive government-service-style shell, sign-in screen and live dashboard tables.
- Local-development login includes one-click demo access for all eight account roles; shared demo credentials and shortcuts are hidden from production builds.
- In local development only, submitting the sign-in form with both credential fields empty opens the demo Administrator workspace; entering either credential keeps normal authentication in effect.
- Account creation uses a responsive five-step wizard with validation, requested-role review and a registration status handoff; submissions remain pending until required verification and approval.
- Every requested account type can optionally submit an institution/employee ID-card image; JPEG/PNG content is validated, metadata-stripped, privately stored, and visible only to authorized reviewers through an audited endpoint.
- Premium responsive operations console with routed workspace views for overview, institutions, FDR registry, verification, documents, discrepancies, release/refund and policy configuration.
- Maturity calendar, custody register, reports/export and audit explorer views connected to persisted backend records.
- Consistent loading, empty, error, success and confirmation-oriented form states; live search/filter controls and real API-backed create/upload actions.
- Docker Compose PostgreSQL health check and backend container.
- Detailed FDR registration workflow matching the supplied reference screens: approval case, bank/branch/IFSC, amount in words, issue/maturity dates, beneficiary, joint holder and lien endorsement.
- Backend validation for positive principal, IFSC format, maturity after issue date and required lien clause; registration tests cover persistence and invalid submissions.
- AICTE institution catalogue loaded from `all-institutions-with-programmes.json`: institution metadata and 58,405 programme records are persisted and available to directory filters, institution detail views, dashboard coverage metrics and FDR workflows.

## Remaining implementation

- Durable import execution with staged row payloads and import commit.
- Versioned policy activation and assessment history.
- PDF extraction/OCR provider integration and review provenance.
- Verification evidence, custody, reminders and notification delivery history.
- Release/refund execution evidence, custody and notification history.
- Expanded pagination/filtering UI and end-to-end browser tests.
- Full browser automation could not be run in this environment because the Playwright browser binary is not installed.
- Full institution-level user isolation and the complete production role matrix still require user-to-institution membership data.
- Production object storage, OCR, mail/SMS and authorized bank API configuration.
- A production evidence-retention and deletion policy for private identity images must be established before collecting real applicants' documents.
- Approval-case records are currently represented by the persisted approval-case reference on the FDR; a full approval-case aggregate remains a later enhancement.

The current slice is intentionally database-backed and does not use hardcoded dashboard values.
