# VaultTrace implementation status

## Completed foundation

- FastAPI service with SQLAlchemy models and configurable SQLite/PostgreSQL connection.
- Alembic initial migration scaffold.
- JWT authentication, bootstrap administrator and backend-enforced roles.
- Institution and FDR registry APIs with duplicate validation and explicit lifecycle transitions.
- Private document upload with MIME allow-list, size limit, SHA-256 persistence and duplicate hash rejection.
- Instrument version records, field-level provenance, persisted discrepancies, verification cases and controlled release/refund requests.
- Policy rule records, policy-aware deposit assessment records, CSV import preview/error history, and permission-checked private document retrieval.
- Append-only audit event records for core mutations.
- Dashboard aggregates queried from the database.
- React/TypeScript responsive government-service-style shell, sign-in screen and live dashboard tables.
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
- Approval-case records are currently represented by the persisted approval-case reference on the FDR; a full approval-case aggregate remains a later enhancement.

The current slice is intentionally database-backed and does not use hardcoded dashboard values.
