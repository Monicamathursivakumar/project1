# VaultTrace feature parity review

This review compares the supplied master project document with the existing UI and backend after the current implementation pass. The existing sidebar, typography, navy/teal visual language, cards, tables, modal forms and responsive shell were preserved.

| Requirement area | Existing UI before pass | Backend before pass | Current implementation | Verification |
|---|---|---|---|---|
| Authentication and roles | Login and role display | JWT with admin/officer/reviewer/viewer | Login content type fixed; added custody, auditor and policy-admin role values; backend checks remain authoritative | Authentication smoke test; backend tests |
| Institution directory | Search, table, add form | List/create and CSV preview/import | Preserved; import preview, row errors, duplicate detection and import history remain API-backed; catalogue search now covers names, codes and AICTE identifiers with bounded pagination | `test_institution_csv_preview_and_import`; `test_institution_pagination_and_identifier_search` |
| Deposit assessment | No dedicated view | Policy and assessment endpoints | Policy configuration view and policy-required assessment behavior are connected; assessments now require an active policy within its effective period and retain the selected policy reference | `test_policy_assessment_requires_configured_rule_or_marks_pending`; `test_policy_activation_requires_current_effective_period` |
| FDR registry | Search, status filter, create form | Create/list/status transitions | Preserved; initial instrument version and lifecycle event are persisted | Backend tests and build |
| Document management | Evidence upload view | Private upload/download, MIME/size/hash checks | Preserved; upload remains private and hash-confirmed | Backend upload/download routes |
| OCR and extraction | Guidance only | Not available | PyMuPDF extracts embedded PDF text and Tesseract processes scanned PDFs and image evidence; results remain candidate evidence with no false authenticity or bank-confirmation claim | `test_pdf_extraction_persists_text_without_claiming_authenticity` |
| Provenance | Provenance explanation | L0-L3 field provenance endpoint | Preserved in evidence UX and API | API surface verified |
| Verification | Queue view | Verification case/status endpoint | Preserved; terminal verified/rejected decisions require a traceable evidence reference; each Open Case link routes with its FDR id into the discrepancy centre | `test_terminal_verification_requires_evidence_reference`; browser workflow smoke check |
| Discrepancies | Instrument selector, findings and embedded review chat | Create/list/resolve/waive | Selected-FDR rule-based analysis compares stored fields, OCR, document fingerprints and field provenance; findings cite sources and persist reviewer decisions/history. Embedded chat answers from those authorized records and cites sources; it is not an external LLM or authenticity check | `test_discrepancy_analysis_is_scoped_and_review_actions_are_audited`; chat API test; frontend build |
| Lifecycle timeline | Not exposed | Status transitions existed | Added persisted lifecycle event records and timeline endpoint | API route and migration |
| Maturity monitoring | Missing | Missing | Added maturity calendar view with overdue/upcoming calculation | Frontend build and endpoint |
| Notifications | Missing | Missing | Added persisted notification scheduling/history endpoints, institution scoping, and an auditable unavailable state when external email/SMS delivery is not configured | `test_notification_delivery_boundary_marks_external_channel_unavailable` |
| Renewal/replacement | Missing | Instrument versions only | Verified instruments can enter a governed renewal/replacement review; the original instrument is preserved, a linked version snapshot is created, and scrutiny reopens in draft status | `test_renewal_request_creates_linked_version_and_reopens_scrutiny` |
| Release/refund | Request form | Request/decision endpoints | Preserved; list and institution scoping added, with independent execution and closure evidence controls | `test_release_closure_cannot_be_performed_by_executor` |
| Custody | Missing | Missing | Added custody register view and append-only custody event APIs | Frontend build and API |
| Reports and exports | Missing | Missing | Added permission-checked CSV instrument export with institution scoping for assigned users and audit records for each export | `test_instrument_export_is_scoped_and_audited` |
| Audit explorer | Missing | Audit records existed | Added admin/auditor audit explorer view and filtered API | API surface |
| Dashboard | Live cards and chart | Database aggregate endpoint | Preserved and still database-backed; aggregate counts are institution-scoped for assigned users | `test_aggregate_views_are_scoped_to_membership` |
| Security controls | Protected APIs and private files | Role checks, duplicate checks, self-approval block | Extended role-aware operations, private retrieval, execution independence, export permissions, institution membership isolation, and admin-only policy activation/deactivation | Backend tests and API validation |

## Deliberate limitations

- PDF text extraction uses PyMuPDF when embedded text exists and falls back to the local Tesseract provider for scanned pages; PNG/JPEG evidence also uses Tesseract. Extraction is never treated as authenticity evidence.
- No live bank confirmation is claimed.
- Notification records are scheduled/planned; no email or SMS is marked delivered without an external provider.
- Policy values remain configurable and are not invented.
- The production role matrix needs an institution-to-user relationship for strict institution-level data isolation.
- Institution membership is now persisted and enforced for scoped users; administrators and auditors retain cross-institution oversight.
- Dashboard, catalogue summaries, maturity monitoring, notifications, and exports use the same institution scope.
- Browser end-to-end coverage remains limited by the local Playwright runtime installation.
