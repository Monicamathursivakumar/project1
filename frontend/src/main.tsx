import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, DragEvent, ReactNode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import "./palette.css";

const configuredApiUrl = import.meta.env.VITE_API_URL?.trim().replace(/\/+$/, "");
const API = configuredApiUrl
  ? /^https?:\/\//i.test(configuredApiUrl) ? configuredApiUrl : `https://${configuredApiUrl}`
  : "http://127.0.0.1:8000";

type Summary = { institutions: number; fdrs: number; verified: number; pending: number };
type User = { id: number; username: string; role: string };
type DemoAccount = { username: string; label: string; role: string; description: string };
const demoPassword = "VaultTrace-Demo-2026!";
const demoAccounts: DemoAccount[] = [
  { username: "demo_institution_user", label: "Institution User", role: "Institution User", description: "Institution-scoped FDR records" },
  { username: "demo_reviewing_officer", label: "Reviewing Officer", role: "Reviewing Officer", description: "Review and discrepancy queues" },
  { username: "demo_verification_officer", label: "Verification Officer", role: "Verification Officer", description: "Instrument verification work" },
  { username: "demo_custody_officer", label: "Custody Officer", role: "Custody Officer", description: "Custody register and handovers" },
  { username: "demo_policy_administrator", label: "Policy Administrator", role: "Policy Administrator", description: "View policy configuration" },
  { username: "demo_auditor", label: "Auditor", role: "Auditor", description: "Read-only audit and reports" },
  { username: "demo_administrator", label: "Administrator", role: "Administrator", description: "User and system administration" },
  { username: "demo_viewer", label: "Viewer", role: "Viewer", description: "Read-only workspace access" },
];
type Institution = { id: number; name: string; code: string; address: string; aicte_id?: string; other_id?: string; district: string; state: string; institution_type: string; women: string; minority: string; university: string };
type RegistrationInstitution = { id: number; name: string; code: string };
type RegistrationStatus = { registration_id: string; account_type: string; status: string; email_verification: string; identity_verification: string; employee_verification: string; institution_association: string; role_approval: string; updated_at: string; decision_reason?: string };
type RegistrationReview = { id: number; registration_id: string; username: string; full_name: string; email: string; account_type: string; organization_name: string; institution_id: number | null; institution_name: string | null; employee_id: string | null; department: string; designation: string; status: string; email_verified_at: string | null; identity_status: string; employee_status: string; institution_status: string; role_status: string; created_at: string; decision_reason: string; decision_at: string | null; has_identity_document: boolean; identity_document_content_type: string | null; identity_document_size: number | null };
type Programme = { id: number; programme: string; level: string; course: string; course_type: string; shift: string; availability: string; intake: string; enrollment: string; placement: string };
type InstitutionSummary = { institutions: number; programmes: number; states: string[]; institution_types: string[] };
type Fdr = { id: number; identifier: string; institution_id: number; holder_name: string; amount: number; maturity_date: string; status: string; approval_case_reference?: string; bank_name?: string; branch_name?: string; ifsc_code?: string; amount_in_words?: string; issue_date?: string; beneficiary?: string; joint_holder?: string; lien_endorsed?: boolean; lien_clause?: string };
type Policy = { id: number; rule_id: string; description: string; amount_floor: number; version: number; active: boolean; source_reference: string; effective_date: string; expiry_date?: string };
type DiscrepancyHistory = { id: number; actor_id: number; action: string; reason: string; created_at: string };
type Discrepancy = { id: number; fdr_id: number; rule_id: string; title?: string; affected_field?: string; severity: string; explanation: string; expected_value: string; expected_source?: string; observed_value: string; observed_source?: string; evidence_reference?: string; evidence_document_ids?: number[]; recommended_action?: string; analysis_method?: string; status: string; review_status?: string; resolution_notes: string; history?: DiscrepancyHistory[] };
type DiscrepancyChatMessage = { role: "user" | "assistant"; text: string; sources?: string[] };
type DocumentRow = { id: number; fdr_id: number; original_name: string; sha256: string; content_type: string; size: number; created_at: string };
type TimelineRow = { id: number; from_status: string; to_status: string; reason?: string; created_at: string };
type CustodyRow = { id: number; event_type: string; location: string; custodian: string; received_at: string; created_at: string };
type VersionRow = { id: number; version_number: number; change_reason: string; created_at: string; snapshot: string };
type AuditRow = { id: number; actor_id: number; action: string; entity: string; entity_id: string; details: string; created_at: string };
type ReleaseRow = { id: number; fdr_id: number; request_type: string; reason: string; status: string; created_at: string };
type Page = "overview" | "institutions" | "registry" | "instrument-detail" | "verification" | "documents" | "discrepancies" | "release" | "maturity" | "custody" | "reports" | "audit" | "policies" | "accounts";

const navItems: { id: Page; label: string; group: string; icon: string }[] = [
  { id: "overview", label: "Overview", group: "Workspace", icon: "grid" },
  { id: "institutions", label: "Institution directory", group: "Workspace", icon: "building" },
  { id: "registry", label: "FDR records", group: "Workspace", icon: "file" },
  { id: "verification", label: "Verification centre", group: "Operations", icon: "shield" },
  { id: "documents", label: "Upload & Analyze FDR", group: "Operations", icon: "upload" },
  { id: "discrepancies", label: "Discrepancies", group: "Operations", icon: "alert" },
  { id: "release", label: "Release / refund", group: "Lifecycle", icon: "arrow" },
  { id: "maturity", label: "Maturity calendar", group: "Lifecycle", icon: "clock" },
  { id: "custody", label: "Custody register", group: "Lifecycle", icon: "archive" },
  { id: "reports", label: "Reports & exports", group: "Insights", icon: "download" },
  { id: "audit", label: "Audit explorer", group: "Insights", icon: "list" },
  { id: "policies", label: "Policy configuration", group: "Administration", icon: "settings" },
  { id: "accounts", label: "Account approvals", group: "Administration", icon: "shield" },
];

function pageFromLocation(): Page {
  const requested = new URLSearchParams(window.location.search).get("page");
  return navItems.some((item) => item.id === requested) || requested === "instrument-detail"
    ? requested as Page
    : "overview";
}

function discrepancyIdFromLocation(): number | null {
  const value = Number(new URLSearchParams(window.location.search).get("fdrId"));
  return Number.isInteger(value) && value > 0 ? value : null;
}

function publicScreenFromLocation(): "landing" | "auth" {
  const params = new URLSearchParams(window.location.search);
  return ["auth", "page", "verifyEmail", "resetPassword", "registrationId"].some((key) => params.has(key))
    ? "auth"
    : "landing";
}

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    grid: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
    user: "M20 21a8 8 0 00-16 0M12 13a5 5 0 100-10 5 5 0 000 10z",
    building: "M4 20V4h10v16M14 9h6v11M7 8h4M7 12h4M7 16h4M17 13h1M17 17h1",
    file: "M6 3h8l4 4v14H6zM14 3v5h5M9 13h6M9 17h6",
    shield: "M12 3l8 3v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6zM9 12l2 2 4-4",
    paperclip: "M8 12.5l5.5-5.5a3 3 0 114.2 4.2l-7.8 7.8a5 5 0 11-7.1-7.1l7.5-7.5",
    alert: "M12 3l9 17H3zM12 9v4M12 17h.01",
    arrow: "M5 12h14M13 6l6 6-6 6",
    settings: "M12 8a4 4 0 100 8 4 4 0 000-8zM4 12H2m20 0h-2M12 4V2m0 20v-2M5.6 5.6L4.2 4.2m15.6 15.6-1.4-1.4M18.4 5.6l1.4-1.4M4.2 19.8l1.4-1.4",
    search: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3",
    bell: "M18 8a6 6 0 00-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
    plus: "M12 5v14M5 12h14",
    upload: "M12 16V4m0 0L7 9m5-5l5 5M4 20h16",
    logout: "M10 17l5-5-5-5M15 12H3M21 4v16",
    close: "M6 6l12 12M18 6L6 18",
    check: "M5 12l4 4L19 6",
    clock: "M12 7v5l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0",
    archive: "M4 7h16v13H4zM3 4h18v3H3zM9 12h6",
    download: "M12 4v11m0 0l-4-4m4 4l4-4M5 20h14",
    list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={paths[name] || paths.file} /></svg>;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("vaulttrace_token");
  const headers = new Headers(options.headers);
  if (options.body instanceof FormData) {
    headers.delete("Content-Type");
  } else if (options.body instanceof URLSearchParams) {
    headers.set("Content-Type", "application/x-www-form-urlencoded");
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(API + path, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail.map((item: { msg?: string }) => item.msg || "Invalid input").join(", ")
      : body.detail;
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json();
}

function formatAmount(value: number) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(value);
}

type FdrDraftValues = Partial<{
  identifier: string;
  institution_id: string;
  institution_name: string;
  approval_case_reference: string;
  bank_name: string;
  branch_name: string;
  ifsc_code: string;
  amount: string;
  amount_in_words: string;
  issue_date: string;
  maturity_date: string;
  beneficiary: string;
  joint_holder: string;
}>;

function extractCandidateValue(text: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]?.trim()) return match[1].trim().replace(/\s+/g, " ");
  }
  return "";
}

function extractLabeledValue(text: string, labels: string[]) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const label = labels.find((candidate) => new RegExp(`^${candidate}(?:\\s*[:#-]\\s*|\\s{2,})`, "i").test(line));
    if (!label) continue;
    const inline = line.replace(new RegExp(`^${label}\\s*(?:[:#-]\\s*|\\s{2,})`, "i"), "").trim();
    if (inline) return inline;
    if (lines[index + 1]) return lines[index + 1];
  }
  return "";
}

function validFdrIdentifier(value: string) {
  return /^(?:FDR|FD|CERTIFICATE)[A-Z0-9/_-]*\d[A-Z0-9/_-]*$/i.test(value.trim());
}

function validIfsc(value: string) {
  return /^[A-Z]{4}0[A-Z0-9]{6}$/i.test(value.trim());
}

function normalizeCandidateDate(value: string) {
  const match = value.match(/\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b/);
  if (!match) return "";
  const year = match[3].length === 2 ? `20${match[3]}` : match[3];
  return `${year}-${match[2].padStart(2, "0")}-${match[1].padStart(2, "0")}`;
}

function extractFdrDraft(text: string, selectedFdr?: Fdr, institution?: Institution): FdrDraftValues {
  const identifier = extractLabeledValue(text, ["FDR\\s*(?:no|number|id)", "FD\\s*(?:no|number|id)", "certificate\\s*(?:no|number|id)"]) || extractCandidateValue(text, [/(?:FDR|FD|certificate)[ \t]*(?:no|number|id)?[ \t]*[:#-]?[ \t]*((?=[A-Z0-9/-]*\d)[A-Z0-9][A-Z0-9/-]{4,})/i]);
  const bank = extractLabeledValue(text, ["bank", "issuing bank", "scheduled bank"]) || extractCandidateValue(text, [/(?:name[ \t]+and[ \t]+address[ \t]+of[ \t]+the[ \t]+)?bank[ \t]*[:\-][ \t]*([^\n]+)/i]);
  const branch = extractLabeledValue(text, ["branch", "branch name"]);
  const ifsc = extractLabeledValue(text, ["IFSC", "IFSC code"]) || extractCandidateValue(text, [/\bIFSC(?:[ \t]+code)?[ \t]*[:\-][ \t]*([A-Z]{4}0[A-Z0-9]{6})/i]);
  const amount = extractLabeledValue(text, ["amount", "amount \\(Rs\\.\\)", "principal", "deposit"]) || extractCandidateValue(text, [/(?:amount|principal|deposit)[ \t]*(?:\(?(?:rs\.?|inr)\)?)?[ \t]*[:\-][ \t]*(?:₹|rs\.?|inr)?[ \t]*([\d,]+(?:\.\d{1,2})?)/i]);
  const amountInWords = extractLabeledValue(text, ["amount in words", "rupees"]) || extractCandidateValue(text, [/(?:amount[ \t]+in[ \t]+words|rupees)[ \t]*[:\-][ \t]*([^\n]+)/i]);
  const issueRaw = extractLabeledValue(text, ["date of issue", "issue date"]) || extractCandidateValue(text, [/(?:date[ \t]+of[ \t]+issue|issue[ \t]+date)[ \t]*[:\-][ \t]*([^\n]+)/i]);
  const maturityRaw = extractLabeledValue(text, ["date of maturity", "maturity date"]) || extractCandidateValue(text, [/(?:date[ \t]+of[ \t]+maturity|maturity[ \t]+date)[ \t]*[:\-][ \t]*([^\n]+)/i]);
  const beneficiary = extractLabeledValue(text, ["beneficiary", "in favour of", "in favor of"]) || extractCandidateValue(text, [/(?:beneficiary|in[ \t]+favour[ \t]+of)[ \t]*[:\-][ \t]*([^\n]+)/i]);
  const extractedAmount = amount.replace(/[^\d.,]/g, "").replace(/,/g, "");
  const extractedIssueDate = normalizeCandidateDate(issueRaw);
  const extractedMaturityDate = normalizeCandidateDate(maturityRaw);
  return {
    identifier: validFdrIdentifier(identifier) ? identifier : selectedFdr?.identifier,
    institution_id: selectedFdr ? String(selectedFdr.institution_id) : undefined,
    approval_case_reference: selectedFdr?.approval_case_reference,
    bank_name: bank || selectedFdr?.bank_name,
    branch_name: branch || selectedFdr?.branch_name,
    ifsc_code: validIfsc(ifsc) ? ifsc.toUpperCase() : selectedFdr?.ifsc_code,
    amount: extractedAmount ? extractedAmount : selectedFdr ? String(selectedFdr.amount) : undefined,
    amount_in_words: amountInWords || selectedFdr?.amount_in_words,
    issue_date: extractedIssueDate || selectedFdr?.issue_date?.slice(0, 10),
    maturity_date: extractedMaturityDate || selectedFdr?.maturity_date?.slice(0, 10),
    beneficiary: beneficiary || selectedFdr?.beneficiary,
    joint_holder: selectedFdr?.joint_holder || institution?.name,
  };
}

function StatusBadge({ value }: { value?: string }) {
  const label = (value || "unknown").replace(/_/g, " ");
  return <span className={`status status-${value || "unknown"}`}><i />{label}</span>;
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [page, setPageState] = useState<Page>(pageFromLocation);
  const [publicScreen, setPublicScreen] = useState<"landing" | "auth">(publicScreenFromLocation);
  const [selectedDiscrepancyFdrId, setSelectedDiscrepancyFdrId] = useState<number | null>(discrepancyIdFromLocation);
  const [selectedInstrument, setSelectedInstrument] = useState<number | null>(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");

  const setPage = (nextPage: Page) => {
    const params = new URLSearchParams(window.location.search);
    params.set("page", nextPage);
    if (nextPage !== "discrepancies") {
      params.delete("fdrId");
      setSelectedDiscrepancyFdrId(null);
    }
    window.history.pushState(null, "", `${window.location.pathname}?${params.toString()}`);
    setPageState(nextPage);
  };
  const openDiscrepancy = (fdrId: number) => {
    const params = new URLSearchParams(window.location.search);
    params.set("page", "discrepancies");
    params.set("fdrId", String(fdrId));
    window.history.pushState(null, "", `${window.location.pathname}?${params.toString()}`);
    setSelectedDiscrepancyFdrId(fdrId);
    setPageState("discrepancies");
  };
  const selectDiscrepancyInstrument = (fdrId: number | null) => {
    const params = new URLSearchParams(window.location.search);
    params.set("page", "discrepancies");
    if (fdrId) params.set("fdrId", String(fdrId));
    else params.delete("fdrId");
    window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
    setSelectedDiscrepancyFdrId(fdrId);
  };

  useEffect(() => {
    const syncLocation = () => {
      setPageState(pageFromLocation());
      setSelectedDiscrepancyFdrId(discrepancyIdFromLocation());
      setPublicScreen(publicScreenFromLocation());
    };
    window.addEventListener("popstate", syncLocation);
    return () => window.removeEventListener("popstate", syncLocation);
  }, []);

  useEffect(() => {
    if (!localStorage.getItem("vaulttrace_token")) { setBooting(false); return; }
    request<User>("/api/auth/me").then(setUser).catch(() => localStorage.removeItem("vaulttrace_token")).finally(() => setBooting(false));
  }, []);

  if (booting) return <div className="loading-screen"><img className="brand-logo loading-logo" src="/aicte-logo.png" alt="AICTE logo" /><span>Loading secure workspace…</span></div>;
  if (!user) {
    const openAuth = (mode: "login" | "register") => {
      const params = new URLSearchParams();
      params.set("auth", mode);
      window.history.pushState(null, "", `${window.location.pathname}?${params.toString()}`);
      setPublicScreen("auth");
    };
    const backToLanding = () => {
      window.history.pushState(null, "", window.location.pathname);
      setPublicScreen("landing");
    };
    if (publicScreen === "landing") return <LandingPage onNavigate={openAuth} />;
    return <Login onLogin={setUser} onBackHome={backToLanding} />;
  }

  const logout = () => { localStorage.removeItem("vaulttrace_token"); setUser(null); setPublicScreen("auth"); };
  return <div className="app-shell">
    <Sidebar page={page} setPage={setPage} role={user.role} onLogout={logout} />
    <div className="app-content">
      <Topbar user={user} onSearch={() => setPage("registry")} />
      <main className="content-wrap">
        <div className="breadcrumbs"><span>VaultTrace</span><b>/</b><strong>{navItems.find((item) => item.id === page)?.label}</strong></div>
        {error && <div className="toast error-toast"><Icon name="alert" size={16} />{error}<button onClick={() => setError("")}><Icon name="close" size={15} /></button></div>}
        <PageContent page={page} setPage={setPage} setError={setError} role={user.role} selectedInstrument={selectedInstrument} selectedDiscrepancyFdrId={selectedDiscrepancyFdrId} openDiscrepancy={openDiscrepancy} selectDiscrepancyInstrument={selectDiscrepancyInstrument} openInstrument={(id) => { setSelectedInstrument(id); setPage("instrument-detail"); }} />
      </main>
    </div>
  </div>;
}

function LandingPage({ onNavigate }: { onNavigate: (mode: "login" | "register") => void }) {
  const workflowStages = [
    ["01", "Submit", "Register an account and provide the details needed for review."],
    ["02", "Verify", "Track email, identity, employee and institution checks separately."],
    ["03", "Review", "Authorized reviewers record decisions and reasons."],
    ["04", "Access", "Role access follows approval—not the applicant's request alone."],
  ];
  const capabilities = [
    ["Evidence-led records", "Keep FDR details, supporting documents and field provenance together for review."],
    ["Clear approval stages", "See where an account, instrument or release request sits in its workflow."],
    ["Controlled decisions", "Use role checks, institution-scoped access and recorded decision history."],
  ];
  const roles = [
    ["Institution teams", "Submit and track records for their associated institution."],
    ["Review & verification", "Inspect evidence, resolve discrepancies and record review outcomes."],
    ["Custody & policy", "Manage custody history and maintain versioned policy settings."],
    ["Audit & administration", "Review activity history and administer access approvals."],
  ];

  return <main className="landing-page">
    <header className="landing-header">
      <a className="landing-brand" href="#home" aria-label="VaultTrace home">
        <img className="brand-logo landing-logo" src="/aicte-logo.png" alt="" />
        <span><b>VAULT<span>TRACE</span></b><small>Security deposit intelligence</small></span>
      </a>
      <nav className="landing-nav" aria-label="Main navigation">
        <a href="#workflow">How it works</a>
        <a href="#capabilities">Platform</a>
        <button className="landing-signin" onClick={() => onNavigate("login")}>Sign in</button>
        <button className="button primary landing-nav-cta" onClick={() => onNavigate("register")}>Request access<Icon name="arrow" size={15} /></button>
      </nav>
    </header>

    <section className="landing-hero" id="home">
      <div className="landing-hero-grid">
        <div className="landing-copy">
          <div className="landing-kicker"><span /> ACCOUNTABLE RECORDS · CONTROLLED WORKFLOWS</div>
          <h1>Every deposit.<br /><em>Clear status.</em><br />Accountable decisions.</h1>
          <p>VaultTrace brings institution records, fixed deposit receipts and review workflows into one carefully controlled workspace.</p>
          <div className="landing-actions">
            <button className="button primary" onClick={() => onNavigate("register")}>Request account access<Icon name="arrow" size={16} /></button>
            <a className="landing-secondary-action" href="#workflow"><span className="landing-play">↓</span> Explore the workflow</a>
          </div>
          <div className="landing-assurance"><Icon name="shield" size={16} /><span>Access is role-based. Decisions are recorded. Evidence remains reviewable.</span></div>
        </div>
        <div className="landing-preview-wrap" aria-label="Illustrative VaultTrace interface preview">
          <div className="landing-preview-glow" />
          <div className="landing-preview">
            <div className="preview-topbar"><span className="preview-mark">V</span><div><b>VaultTrace</b><small>Operations workspace</small></div><span className="preview-demo-label">ILLUSTRATIVE</span></div>
            <div className="preview-body">
              <div className="preview-eyebrow">RECORD OVERVIEW</div>
              <div className="preview-title-row"><div><h2>Deposit records</h2><p>Review status at a glance</p></div><span className="preview-filter">All records⌄</span></div>
              <div className="preview-stat-row">
                <div><small>RECORD DETAILS</small><b>Institution · Bank · Dates</b><span>Structured information</span></div>
                <div><small>REVIEW STATUS</small><b><i /> Under review</b><span>Decision history available</span></div>
              </div>
              <div className="preview-table">
                <div className="preview-table-head"><span>WORKFLOW</span><span>STATUS</span></div>
                <div className="preview-table-row"><span><i className="preview-dot dot-gold" /> Evidence review</span><b>In progress</b></div>
                <div className="preview-table-row"><span><i className="preview-dot dot-blue" /> Verification</span><b>Queued</b></div>
                <div className="preview-table-row"><span><i className="preview-dot dot-slate" /> Decision record</span><b>Audit trail</b></div>
              </div>
              <div className="preview-footer"><Icon name="shield" size={14} /><span>Illustrative preview · not live account data</span></div>
            </div>
          </div>
          <div className="preview-float-card"><span className="preview-float-icon"><Icon name="check" size={17} /></span><span><b>Review with context</b><small>Evidence and decisions together</small></span></div>
        </div>
      </div>
      <div className="landing-proof-strip" aria-label="Platform scope">
        <span><b>8</b> requested account roles</span><i />
        <span>Evidence &amp; decisions connected</span><i />
        <span>Role-based access controls</span>
      </div>
    </section>

    <section className="landing-workflow landing-section" id="workflow">
      <div className="landing-section-heading">
        <div className="landing-eyebrow">A clearer path from submission to decision</div>
        <h2>One workspace for the<br /><em>whole review journey.</em></h2>
        <p>Replace scattered handoffs with a shared view of the record, its supporting evidence and the next responsible action.</p>
      </div>
      <div className="landing-stage-grid">
        {workflowStages.map(([number, title, description]) => <article className="landing-stage" key={number}>
          <span className="stage-number">{number}</span><span className="stage-line" />
          <h3>{title}</h3><p>{description}</p>
        </article>)}
      </div>
    </section>

    <section className="landing-capabilities" id="capabilities">
      <div className="landing-capabilities-inner">
        <div className="landing-capabilities-copy">
          <div className="landing-eyebrow">Built around responsible operations</div>
          <h2>Information in context.<br /><em>Action with accountability.</em></h2>
          <p>VaultTrace is designed to help teams move from record handling to informed, traceable decisions—without treating automation as proof.</p>
          <button className="landing-outline-button" onClick={() => onNavigate("register")}>See the workflow in action<Icon name="arrow" size={15} /></button>
        </div>
        <div className="landing-capability-list">
          {capabilities.map(([title, description], index) => <article className="landing-capability" key={title}>
            <span>0{index + 1}</span><div><h3>{title}</h3><p>{description}</p></div><Icon name="arrow" size={16} />
          </article>)}
        </div>
      </div>
    </section>

    <section className="landing-roles landing-section">
      <div className="landing-section-heading">
        <div className="landing-eyebrow">Designed for accountable teams</div>
        <h2>The right view for<br /><em>every responsibility.</em></h2>
      </div>
      <div className="landing-role-grid">{roles.map(([title, description], index) => <article className="landing-role" key={title}>
        <span className="landing-role-index">0{index + 1}</span><h3>{title}</h3><p>{description}</p>
      </article>)}</div>
    </section>

    <section className="landing-final">
      <div className="landing-final-inner">
        <div className="landing-eyebrow">Start with a clear process</div>
        <h2>Better records make<br /><em>better decisions possible.</em></h2>
        <p>Request access to VaultTrace and follow the review steps for your role.</p>
        <div className="landing-actions landing-final-actions">
          <button className="button primary" onClick={() => onNavigate("register")}>Create an account request<Icon name="arrow" size={16} /></button>
          <button className="landing-final-login" onClick={() => onNavigate("login")}>Already have access? Sign in</button>
        </div>
      </div>
    </section>
    <footer className="landing-footer">
      <a className="landing-brand" href="#home"><img className="brand-logo landing-logo" src="/aicte-logo.png" alt="" /><span><b>VAULT<span>TRACE</span></b><small>Security deposit intelligence</small></span></a>
      <span>Independent SIH 2026 prototype · Not an official government portal</span>
      <a href="#home">Back to top ↑</a>
    </footer>
  </main>;
}

function Login({ onLogin, onBackHome }: { onLogin: (user: User) => void; onBackHome: () => void }) {
  const params = new URLSearchParams(window.location.search);
  const [mode, setMode] = useState<"login" | "register" | "status" | "forgot" | "reset">(
    params.has("resetPassword") ? "reset" : params.has("registrationId") || params.get("auth") === "status" ? "status" : params.get("auth") === "register" ? "register" : "login",
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [resetToken, setResetToken] = useState(params.get("resetPassword") || "");
  const [registrationId, setRegistrationId] = useState(params.get("registrationId") || "");
  const [statusEmail, setStatusEmail] = useState("");
  const authCardRef = useRef<HTMLElement>(null);
  const [verificationMessage, setVerificationMessage] = useState(
    params.get("github") === "verified"
      ? "GitHub account ownership was checked. This does not verify identity, employment or authorization."
      : params.get("github") === "denied" ? "GitHub verification was cancelled or declined. Your registration can continue without it." : "",
  );
  useEffect(() => {
    if (!new URLSearchParams(window.location.search).has("verifyEmail")
      && (params.has("resetPassword") || params.has("github"))) {
      window.history.replaceState(null, "", window.location.pathname);
    }
    const token = new URLSearchParams(window.location.search).get("verifyEmail");
    if (!token) return;
    setLoading(true);
    request<RegistrationStatus>("/api/auth/email/verify", { method: "POST", body: JSON.stringify({ token }) })
      .then((result) => {
        setRegistrationId(result.registration_id);
        setMode("status");
        setVerificationMessage("Email verified. Identity and organization checks are separate and may still be pending.");
        window.history.replaceState(null, "", window.location.pathname);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => {
    const resetAuthScroll = () => {
      authCardRef.current?.scrollTo(0, 0);
      window.scrollTo(0, 0);
    };
    resetAuthScroll();
    const frame = requestAnimationFrame(resetAuthScroll);
    return () => cancelAnimationFrame(frame);
  }, [mode]);
  const signIn = async (credentials: Pick<DemoAccount, "username"> & { password: string } = { username, password }) => {
    setLoading(true); setError("");
    try {
      setUsername(credentials.username);
      setPassword(credentials.password);
      const body = new URLSearchParams(credentials);
      const token = await request<{ access_token: string }>("/api/auth/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
      localStorage.setItem("vaulttrace_token", token.access_token);
      onLogin(await request<User>("/api/auth/me"));
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (import.meta.env.DEV && !username.trim() && !password) {
      await signIn({ username: "demo_administrator", password: demoPassword });
      return;
    }
    await signIn();
  };
  const requestReset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setLoading(true); setError(""); setNotice("");
    try {
      const form = new FormData(event.currentTarget);
      const result = await request<{ message: string }>("/api/auth/password-reset/request", { method: "POST", body: JSON.stringify({ email: form.get("email") }) });
      setNotice(result.message);
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  };
  const confirmReset = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setLoading(true); setError(""); setNotice("");
    try {
      const form = new FormData(event.currentTarget);
      const result = await request<{ message: string }>("/api/auth/password-reset/confirm", { method: "POST", body: JSON.stringify({ token: resetToken, password: form.get("password") }) });
      setNotice(result.message);
      setMode("login");
      window.history.replaceState(null, "", window.location.pathname);
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  };
  const switchMode = (next: typeof mode) => {
    setError(""); setNotice(""); setMode(next);
    if (["login", "register", "status"].includes(next)) {
      const nextParams = new URLSearchParams();
      if (next === "status" && registrationId) nextParams.set("registrationId", registrationId);
      else nextParams.set("auth", next);
      window.history.pushState(null, "", `${window.location.pathname}?${nextParams.toString()}`);
    }
  };
  const heading = mode === "login" ? "Welcome back" : mode === "register" ? "Create your account" : mode === "status" ? "Registration status" : mode === "forgot" ? "Reset your password" : "Choose a new password";
  const cardClass = [
    "login-card",
    mode === "register" || mode === "status" ? "auth-card-wide" : "",
    mode === "login" && import.meta.env.DEV ? "auth-card-demo" : "",
  ].filter(Boolean).join(" ");
  const pageClass = [
    "login-page",
    mode === "register" || mode === "status" || (mode === "login" && import.meta.env.DEV) ? "login-page-expanded" : "",
  ].filter(Boolean).join(" ");
  return <main className={pageClass}>
    <div className="login-art">
      <div className="login-orbit orbit-one" />
      <div className="login-orbit orbit-two" />
      <div className="login-art-copy">
        <div className="brand-lockup"><img className="brand-logo login-logo" src="/aicte-logo.png" alt="AICTE logo" /><div><b>VAULT<span>TRACE</span></b><small>Security deposit intelligence</small></div></div>
        <h1>Every instrument.<br /><em>Accountable.</em></h1>
        <p>A secure workspace for institution records, FDR verification and controlled lifecycle decisions.</p>
        <div className="assurance"><Icon name="shield" size={19} /><span>Evidence-led, policy-aware and audit ready</span></div>
      </div>
    </div>
    <section className={cardClass} ref={authCardRef}>
      <button className="auth-home-button" type="button" onClick={onBackHome}>← VaultTrace home</button>
      <div className="mobile-brand"><img className="brand-logo mobile-logo" src="/aicte-logo.png" alt="AICTE logo" /><b>VAULT<span>TRACE</span></b></div>
      <div className="eyebrow">SIH 2026 PROTOTYPE</div>
      <h2>{heading}</h2>
      <p className="muted">{mode === "login" ? "Sign in to your secure operations workspace." : mode === "register" ? "Request access through the five-step review process." : "Use your request details to continue securely."}</p>
      {notice && <div className="success-message auth-message" role="status">{notice}</div>}
      {verificationMessage && <div className="success-message auth-message" role="status">{verificationMessage}</div>}
      {error && <div className="form-error auth-message" role="alert"><Icon name="alert" size={15} />{error}</div>}
      {mode === "login" && <>
        <form onSubmit={submit}>
          <label htmlFor="login-username">Username<input id="login-username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required={!import.meta.env.DEV} /></label>
          <label htmlFor="login-password">Password<input id="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required={!import.meta.env.DEV} /></label>
          <button className="button primary wide" disabled={loading}>{loading ? "Opening workspace…" : "Sign in securely"}<Icon name="arrow" size={17} /></button>
          <div className="auth-links"><button type="button" onClick={() => switchMode("register")}>Create Account</button><button type="button" onClick={() => switchMode("forgot")}>Forgot Password?</button></div>
          <button className="auth-text-button" type="button" onClick={() => switchMode("status")}>Check registration status / resend verification</button>
          <button className="auth-text-button" type="button" onClick={() => { setError(""); setNotice("Contact your VaultTrace system administrator through your organization’s support channel."); }}>Contact Administrator</button>
        </form>
        {import.meta.env.DEV && <section className="demo-login" aria-labelledby="demo-login-title">
          <div className="demo-login-heading">
            <span className="demo-environment"><i /> Local demo</span>
            <h3 id="demo-login-title">Explore by role</h3>
            <p>Choose a demo account to sign in and compare the role-specific workspace.</p>
          </div>
          <div className="demo-role-grid">
            {demoAccounts.map((account) => <button className="demo-role-card" type="button" key={account.username} onClick={() => void signIn({ username: account.username, password: demoPassword })} disabled={loading} aria-label={`Sign in as ${account.role}`}>
              <span className="demo-role-mark" aria-hidden="true">{account.label.slice(0, 1)}</span>
              <span className="demo-role-copy"><b>{account.label}</b><small>{account.description}</small><code>{account.username}</code></span>
              <span className="demo-role-action">{loading ? "Opening…" : "Sign in"}<Icon name="arrow" size={14} /></span>
            </button>)}
          </div>
          <p className="demo-password-note">Shared demo password <code>{demoPassword}</code>. Demo shortcuts are available only in local development.</p>
        </section>}
      </>}
      {mode === "register" && <RegistrationWizard onComplete={(id, email, message) => {
        setRegistrationId(id); setStatusEmail(email); setNotice(message); setVerificationMessage(""); setError(""); setMode("status");
        const nextParams = new URLSearchParams();
        nextParams.set("registrationId", id);
        window.history.pushState(null, "", `${window.location.pathname}?${nextParams.toString()}`);
      }} onCancel={() => switchMode("login")} />}
      {mode === "status" && <RegistrationStatusScreen registrationId={registrationId} initialEmail={statusEmail} initialMessage={verificationMessage} onBack={() => switchMode("login")} onError={setError} onNotice={setNotice} />}
      {mode === "forgot" && <form onSubmit={requestReset}><label htmlFor="reset-email">Account email<input id="reset-email" name="email" type="email" autoComplete="email" required /></label><button className="button primary wide" disabled={loading}>{loading ? "Sending…" : "Send reset instructions"}</button><button type="button" className="auth-text-button" onClick={() => switchMode("login")}>Back to sign in</button></form>}
      {mode === "reset" && <form onSubmit={confirmReset}><label htmlFor="reset-token">Reset token<input id="reset-token" value={resetToken} onChange={(e) => setResetToken(e.target.value)} required minLength={20} autoComplete="one-time-code" /></label><label htmlFor="new-password">New password<input id="new-password" name="password" type="password" required minLength={12} maxLength={128} autoComplete="new-password" /></label><button className="button primary wide" disabled={loading}>{loading ? "Updating…" : "Set new password"}</button><button type="button" className="auth-text-button" onClick={() => switchMode("login")}>Back to sign in</button></form>}
      <small className="login-foot">Independent prototype · Not an official government portal</small>
    </section>
  </main>;
}

const accountTypes = [
  ["institution_user", "Institution User"],
  ["reviewing_officer", "Reviewing Officer"],
  ["verification_officer", "Verification Officer"],
  ["custody_officer", "Custody Officer"],
  ["policy_administrator", "Policy Administrator"],
  ["auditor", "Auditor"],
  ["administrator", "Administrator"],
  ["viewer", "Viewer"],
] as const;

function RegistrationWizard({ onComplete, onCancel }: { onComplete: (id: string, email: string, message: string) => void; onCancel: () => void }) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [institutions, setInstitutions] = useState<RegistrationInstitution[]>([]);
  const [identityCard, setIdentityCard] = useState<File | null>(null);
  const identityCardInput = useRef<HTMLInputElement>(null);
  const [values, setValues] = useState({
    fullName: "", username: "", email: "", password: "", confirmation: "",
    accountType: "institution_user", organizationName: "", employeeId: "",
    department: "", designation: "", institutionId: "", consent: false,
  });
  useEffect(() => {
    request<RegistrationInstitution[]>("/api/auth/registration-institutions")
      .then(setInstitutions)
      .catch((e) => setError(`Institution list could not be loaded: ${(e as Error).message}`));
  }, []);
  const set = (key: keyof typeof values, value: string | boolean) => setValues((current) => ({ ...current, [key]: value }));
  const employeeRequired = !["institution_user", "viewer"].includes(values.accountType);
  const selectedInstitution = institutions.find((item) => String(item.id) === values.institutionId);
  const validationError = (targetStep: number) => {
    if (targetStep === 1) {
      if (!values.fullName.trim() || values.username.trim().length < 3 || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(values.email)) {
        return "Enter your full name, a username with at least 3 characters and a valid email address.";
      }
      if (values.password.length < 12 || values.password.length > 128 || values.password !== values.confirmation) {
        return "Use a password of 12–128 characters and make sure both password fields match.";
      }
    }
    if (targetStep === 2 && employeeRequired && (!values.organizationName.trim() || !values.employeeId.trim() || !values.department.trim() || !values.designation.trim())) {
      return "Enter your organization, employee ID, department and designation for this requested role.";
    }
    if (targetStep === 4 && values.accountType === "institution_user" && !values.institutionId) {
      return "Select the institution you are requesting to join.";
    }
    return "";
  };
  const continueStep = () => {
    setError("");
    setStep((current) => Math.min(current + 1, 5));
  };
  const submit = async () => {
    for (const targetStep of [1, 2, 4]) {
      const validationMessage = validationError(targetStep);
      if (validationMessage) {
        setStep(targetStep);
        setError(validationMessage);
        return;
      }
    }
    if (!values.consent) { setError("Confirm the consent statement before submitting."); return; }
    setBusy(true); setError("");
    try {
      const registration = {
        username: values.username,
        full_name: values.fullName,
        email: values.email,
        password: values.password,
        password_confirmation: values.confirmation,
        account_type: values.accountType,
        organization_name: values.accountType === "institution_user" ? selectedInstitution?.name || "" : values.organizationName,
        institution_id: values.institutionId ? Number(values.institutionId) : null,
        employee_id: employeeRequired ? values.employeeId : null,
        department: employeeRequired ? values.department : "",
        designation: employeeRequired ? values.designation : "",
        consent: values.consent,
      };
      let result: { registration_id: string; email_delivery: string; message: string };
      if (identityCard) {
        const formData = new FormData();
        formData.append("registration_data", JSON.stringify(registration));
        formData.append("identity_card", identityCard);
        result = await request<{ registration_id: string; email_delivery: string; message: string }>("/api/auth/register-with-evidence", {
          method: "POST",
          body: formData,
        });
      } else {
        result = await request<{ registration_id: string; email_delivery: string; message: string }>("/api/auth/register", {
        method: "POST",
          body: JSON.stringify(registration),
        });
      }
      onComplete(result.registration_id, values.email, result.message);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const roleLabel = accountTypes.find(([value]) => value === values.accountType)?.[1] || "Requested role";
  return <section className="registration-wizard" aria-label="Account registration">
    <ol className="registration-steps" aria-label="Registration progress">{["Personal", "Organization", "Verification", "Association", "Review"].map((label, index) => <li key={label} className={step === index + 1 ? "active" : step > index + 1 ? "complete" : ""}><span>{index + 1}</span><small>{label}</small></li>)}</ol>
    <div className="registration-step-content">
      {step === 1 && <div className="auth-form-grid">
        <label className="auth-field-wide" htmlFor="reg-name">Full name<input id="reg-name" autoComplete="name" value={values.fullName} onChange={(e) => set("fullName", e.target.value)} required /></label>
        <label htmlFor="reg-username">Username<input id="reg-username" autoComplete="username" minLength={3} maxLength={100} value={values.username} onChange={(e) => set("username", e.target.value)} required /></label>
        <label htmlFor="reg-email">Official email<input id="reg-email" type="email" autoComplete="email" value={values.email} onChange={(e) => set("email", e.target.value)} required /></label>
        <label htmlFor="reg-password">Password<input id="reg-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} value={values.password} onChange={(e) => set("password", e.target.value)} required /><small>At least 12 characters.</small></label>
        <label htmlFor="reg-confirm">Confirm password<input id="reg-confirm" type="password" autoComplete="new-password" minLength={12} maxLength={128} value={values.confirmation} onChange={(e) => set("confirmation", e.target.value)} required /></label>
      </div>}
      {step === 2 && <div className="auth-form-grid">
        <label className="auth-field-wide" htmlFor="reg-role">Requested account type<select id="reg-role" value={values.accountType} onChange={(e) => set("accountType", e.target.value)}>{accountTypes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><small>This is a request only. An administrator approves all role assignments.</small></label>
        {employeeRequired ? <>
          <label htmlFor="reg-org">Organization name<input id="reg-org" value={values.organizationName} onChange={(e) => set("organizationName", e.target.value)} required /></label>
          <label htmlFor="reg-employee">Employee ID<input id="reg-employee" value={values.employeeId} onChange={(e) => set("employeeId", e.target.value)} required /></label>
          <label htmlFor="reg-department">Department<input id="reg-department" value={values.department} onChange={(e) => set("department", e.target.value)} required /></label>
          <label htmlFor="reg-designation">Designation<input id="reg-designation" value={values.designation} onChange={(e) => set("designation", e.target.value)} required /></label>
        </> : <div className="auth-note auth-field-wide"><b>{roleLabel}</b><span>{values.accountType === "institution_user" ? "You will select the institution you want to join in the next step." : "Viewer access is read-only and still subject to identity and role review."}</span></div>}
      </div>}
      {step === 3 && <div className="registration-verification-step">
        <div className="auth-note"><b>Verification is reviewed in separate stages</b><span>First verify control of your email. Authorized reviewers then assess identity and, where applicable, employment and institution association. An uploaded image supports manual review but does not prove identity or employment by itself.</span></div>
        <label className="identity-upload-field" htmlFor="reg-identity-card">Institution or employee ID card image <span>Optional · JPEG or PNG · up to 5 MB</span>
          <input ref={identityCardInput} id="reg-identity-card" type="file" accept="image/jpeg,image/png" onChange={(event) => {
            const file = event.target.files?.[0] || null;
            if (file && !["image/jpeg", "image/png"].includes(file.type)) {
              setIdentityCard(null);
              event.target.value = "";
              setError("Choose a JPEG or PNG image for the ID card.");
              return;
            }
            if (file && file.size > 5 * 1024 * 1024) {
              setIdentityCard(null);
              event.target.value = "";
              setError("The ID card image must be 5 MB or smaller.");
              return;
            }
            setError("");
            setIdentityCard(file);
          }} />
        </label>
        {identityCard && <div className="identity-upload-selected"><span>{identityCard.name} · {(identityCard.size / (1024 * 1024)).toFixed(2)} MB</span><button type="button" className="auth-text-button" onClick={() => { setIdentityCard(null); if (identityCardInput.current) identityCardInput.current.value = ""; }}>Remove image</button></div>}
        <p className="identity-upload-privacy">Only authorized registration reviewers can view this private image. Avoid uploading Aadhaar or other unnecessary government ID documents.</p>
      </div>}
      {step === 4 && <div className="auth-form-grid">
        <label className="auth-field-wide" htmlFor="reg-institution">{values.accountType === "institution_user" ? "Institution you are requesting to join" : "Institution association (optional)"}<select id="reg-institution" value={values.institutionId} onChange={(e) => set("institutionId", e.target.value)} required={values.accountType === "institution_user"}><option value="">Select an institution</option>{institutions.map((item) => <option value={item.id} key={item.id}>{item.name}{item.code ? ` (${item.code})` : ""}</option>)}</select>{values.accountType !== "institution_user" && <small>Leave blank if the requested role is not associated with a single institution.</small>}</label>
      </div>}
      {step === 5 && <div className="registration-review">
        <dl><dt>Name</dt><dd>{values.fullName}</dd><dt>Username</dt><dd>{values.username}</dd><dt>Official email</dt><dd>{values.email}</dd><dt>Requested role</dt><dd>{roleLabel}</dd><dt>Organization</dt><dd>{selectedInstitution?.name || values.organizationName || "Not provided"}</dd><dt>Department / designation</dt><dd>{employeeRequired ? `${values.department} / ${values.designation}` : "Not applicable"}</dd><dt>Employee ID</dt><dd>{employeeRequired ? values.employeeId : "Not applicable"}</dd><dt>Institution association</dt><dd>{selectedInstitution?.name || "None requested"}</dd></dl>
        <label className="consent-control"><input type="checkbox" checked={values.consent} onChange={(e) => set("consent", e.target.checked)} />I confirm that the information is accurate and consent to its use for account verification and access review.</label>
        <p className="auth-disclaimer">Your account stays inactive until email, required verification and role approval are complete.</p>
      </div>}
    </div>
    {error && <div className="form-error" role="alert"><Icon name="alert" size={15} />{error}</div>}
    <div className="registration-actions"><button type="button" className="button ghost" onClick={step === 1 ? onCancel : () => { setError(""); setStep(step - 1); }}>{step === 1 ? "Back to sign in" : "Previous"}</button>{step < 5 ? <button type="button" className="button primary" onClick={continueStep}>Continue <Icon name="arrow" size={15} /></button> : <button type="button" className="button primary" onClick={submit} disabled={busy}>{busy ? "Submitting…" : "Submit registration"}</button>}</div>
  </section>;
}

function RegistrationStatusScreen({ registrationId, initialEmail, initialMessage, onBack, onError, onNotice }: { registrationId: string; initialEmail: string; initialMessage: string; onBack: () => void; onError: (message: string) => void; onNotice: (message: string) => void }) {
  const [id, setId] = useState(registrationId);
  const [email, setEmail] = useState(initialEmail);
  const [status, setStatus] = useState<RegistrationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [githubBusy, setGithubBusy] = useState(false);
  const [institutions, setInstitutions] = useState<RegistrationInstitution[]>([]);
  useEffect(() => {
    request<RegistrationInstitution[]>("/api/auth/registration-institutions").then(setInstitutions).catch(() => setInstitutions([]));
  }, []);
  const lookup = async (event?: FormEvent) => {
    event?.preventDefault(); onError(""); onNotice(""); setBusy(true);
    try { setStatus(await request<RegistrationStatus>(`/api/auth/registration-status/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify({ email }) })); }
    catch (e) { onError((e as Error).message); setStatus(null); }
    finally { setBusy(false); }
  };
  useEffect(() => {
    if (id && email) void lookup();
  }, []);
  const resend = async () => {
    onError(""); onNotice(""); setBusy(true);
    try {
      const result = await request<{ message: string }>(`/api/auth/registration-status/${encodeURIComponent(id)}/resend`, { method: "POST", body: JSON.stringify({ email }) });
      onNotice(result.message);
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  };
  const verifyGithub = async () => {
    onError(""); setGithubBusy(true);
    try {
      const result = await request<{ authorization_url: string }>(`/api/auth/github/start?registration_id=${encodeURIComponent(id)}`);
      window.location.assign(result.authorization_url);
    } catch (e) { onError((e as Error).message); setGithubBusy(false); }
  };
  const resubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); onError(""); onNotice(""); setBusy(true);
    try {
      const form = new FormData(event.currentTarget);
      const result = await request<{ registration_id: string; status: string; email_delivery: string; message: string }>(`/api/auth/registration-status/${encodeURIComponent(id)}/resubmit`, {
        method: "POST",
        body: JSON.stringify({
          email,
          full_name: form.get("full_name"),
          organization_name: form.get("organization_name"),
          institution_id: form.get("institution_id") ? Number(form.get("institution_id")) : null,
          employee_id: form.get("employee_id") || null,
          department: form.get("department"),
          designation: form.get("designation"),
        }),
      });
      setStatus({
        registration_id: result.registration_id,
        account_type: status?.account_type || "",
        status: result.status,
        email_verification: "pending",
        identity_verification: "pending",
        employee_verification: status?.account_type && !["institution_user", "viewer"].includes(status.account_type) ? "pending" : "not_required",
        institution_association: status?.account_type === "institution_user" ? "pending" : "not_required",
        role_approval: "pending",
        updated_at: new Date().toISOString(),
      });
      onNotice(result.email_delivery === "sent" ? result.message : `${result.message} Email is not configured; contact the system administrator.`);
    } catch (e) { onError((e as Error).message); } finally { setBusy(false); }
  };
  const stages = [
    ["Email", status?.email_verification || "pending"],
    ["Identity", status?.identity_verification || "pending"],
    ["Employee", status?.employee_verification || "not_required"],
    ["Institution", status?.institution_association || "not_required"],
    ["Role", status?.role_approval || "pending"],
  ];
  return <section className="registration-status">
    {initialMessage && <div className="success-message auth-message" role="status">{initialMessage}</div>}
    <form className="auth-form-grid" onSubmit={lookup}>
      <label className="auth-field-wide" htmlFor="status-id">Registration ID<input id="status-id" value={id} onChange={(e) => setId(e.target.value)} required /></label>
      <label className="auth-field-wide" htmlFor="status-email">Email used for registration<input id="status-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
      <button className="button primary" type="submit" disabled={busy}>{busy ? "Checking…" : "Check status"}</button>
    </form>
    {status && <div className="status-result">
      <div className="status-result-heading"><div><small>REQUEST STATUS</small><h3>{status.status.replace(/_/g, " ")}</h3></div><StatusBadge value={status.status} /></div>
      <div className="approval-progress">{stages.map(([label, value]) => <div key={label} className={`approval-stage status-${value}`}><span>{label}</span><b>{value.replace(/_/g, " ")}</b></div>)}</div>
      {status.decision_reason && <p className="auth-disclaimer">Reviewer note: {status.decision_reason}</p>}
      {status.email_verification === "pending" && <button className="button secondary" type="button" onClick={resend} disabled={busy}>Resend verification email</button>}
      {status.status !== "rejected" && status.status !== "approved" && <button className="button ghost" type="button" onClick={verifyGithub} disabled={githubBusy}>{githubBusy ? "Connecting…" : "Optional: verify GitHub account"}</button>}
      {status.status === "rejected" && <details className="resubmit-details"><summary>Update details and resubmit</summary><form className="auth-form-grid" onSubmit={resubmit}>
        <label className="auth-field-wide">Full name<input name="full_name" required minLength={2} defaultValue="" /></label>
        {!["institution_user", "viewer"].includes(status.account_type) && <>
          <label>Organization name<input name="organization_name" required /></label>
          <label>Employee ID<input name="employee_id" required /></label>
          <label>Department<input name="department" required /></label>
          <label>Designation<input name="designation" required /></label>
        </>}
        <label className="auth-field-wide">Institution association<select name="institution_id" required={status.account_type === "institution_user"} defaultValue=""><option value="">Select an institution</option>{institutions.map((item) => <option key={item.id} value={item.id}>{item.name}{item.code ? ` (${item.code})` : ""}</option>)}</select></label>
        <button className="button primary" disabled={busy}>{busy ? "Submitting…" : "Resubmit request"}</button>
      </form></details>}
      <p className="auth-disclaimer">GitHub confirms account ownership only; it is not proof of identity, employment, student eligibility or institutional authorization.</p>
    </div>}
    <div className="auth-links"><button type="button" onClick={onBack}>Back to sign in</button></div>
  </section>;
}

function Sidebar({ page, setPage, role, onLogout }: { page: Page; setPage: (page: Page) => void; role: string; onLogout: () => void }) {
  const groups = [...new Set(navItems.map((item) => item.group))];
  const canView = (item: { id: Page }) => {
    if (item.id === "policies") return ["admin", "policy_admin"].includes(role);
    if (item.id === "audit") return ["admin", "auditor"].includes(role);
    if (item.id === "custody") return ["admin", "officer", "custody"].includes(role);
    if (item.id === "accounts") return ["admin", "reviewer"].includes(role);
    return true;
  };
  return <aside className="sidebar"><div className="side-brand"><img className="brand-logo sidebar-logo" src="/aicte-logo.png" alt="AICTE logo" /><div><b>VAULT<span>TRACE</span></b><small>SIH 2026 prototype</small></div></div><div className="nav-scroll">{groups.map((group) => <div className="nav-group" key={group}><small>{group}</small>{navItems.filter((item) => item.group === group && canView(item)).map((item) => <button className={page === item.id ? "nav-item active" : "nav-item"} key={item.id} onClick={() => setPage(item.id)}><Icon name={item.icon} /><span>{item.label}</span>{item.id === "discrepancies" && <em>3</em>}</button>)}</div>)}</div><div className="side-footer"><div className="status-live"><i />All systems operational</div><button className="logout" onClick={onLogout}><Icon name="logout" />Sign out</button></div></aside>;
}

function Topbar({ user, onSearch }: { user: User; onSearch: () => void }) {
  return <header className="topbar"><button className="global-search" onClick={onSearch}><Icon name="search" size={17} /><span>Search institutions, FDRs, documents…</span><kbd>⌘ K</kbd></button><div className="top-actions"><button className="icon-button notification" aria-label="Notifications"><Icon name="bell" size={19} /><i /></button><div className="user-chip"><div className="avatar">{user.username.slice(0, 1).toUpperCase()}</div><div><b>{user.username}</b><small>{user.role}</small></div><span className="chevron">⌄</span></div></div></header>;
}

function PageContent({ page, setPage, setError, role, selectedInstrument, selectedDiscrepancyFdrId, openDiscrepancy, selectDiscrepancyInstrument, openInstrument }: { page: Page; setPage: (page: Page) => void; setError: (message: string) => void; role: string; selectedInstrument: number | null; selectedDiscrepancyFdrId: number | null; openDiscrepancy: (id: number) => void; selectDiscrepancyInstrument: (id: number | null) => void; openInstrument: (id: number) => void }) {
  switch (page) {
    case "institutions": return <Institutions setError={setError} role={role} />;
    case "registry": return <Registry setPage={setPage} setError={setError} role={role} openInstrument={openInstrument} />;
    case "instrument-detail": return selectedInstrument ? <InstrumentDetail id={selectedInstrument} setPage={setPage} setError={setError} role={role} /> : <Registry setPage={setPage} setError={setError} role={role} openInstrument={openInstrument} />;
    case "verification": return <Verification setPage={setPage} setError={setError} openDiscrepancy={openDiscrepancy} />;
    case "documents": return <Documents setError={setError} setPage={setPage} />;
    case "discrepancies": return <Discrepancies setError={setError} initialFdrId={selectedDiscrepancyFdrId} onSelectFdr={selectDiscrepancyInstrument} role={role} />;
    case "release": return <Release setError={setError} role={role} />;
    case "maturity": return <Maturity setError={setError} />;
    case "custody": return <Custody setError={setError} />;
    case "reports": return <Reports setError={setError} />;
    case "audit": return <Audit setError={setError} />;
    case "policies": return <Policies setError={setError} role={role} />;
    case "accounts": return <AccountApprovals role={role} setError={setError} />;
    default: return <Overview setPage={setPage} setError={setError} />;
  }
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-header"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}

function AccountApprovals({ role, setError }: { role: string; setError: (message: string) => void }) {
  const [requests, setRequests] = useState<RegistrationReview[]>([]);
  const [users, setUsers] = useState<Array<{ id: number; username: string; email: string | null; role: string; active: boolean }>>([]);
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [identityDocumentPreview, setIdentityDocumentPreview] = useState<{ id: number; url: string } | null>(null);
  const [userAction, setUserAction] = useState<{ userId: number; active: boolean; reason: string } | null>(null);
  const [registrationSearch, setRegistrationSearch] = useState("");
  const [registrationFilter, setRegistrationFilter] = useState("needs_review");
  const [userSearch, setUserSearch] = useState("");
  const [visibleUserLimit, setVisibleUserLimit] = useState(20);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const isAdmin = role === "admin";
  useEffect(() => {
    if (!identityDocumentPreview) return;
    return () => URL.revokeObjectURL(identityDocumentPreview.url);
  }, [identityDocumentPreview]);
  const load = async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [registrationRequests, activeUsers] = await Promise.all([
        request<RegistrationReview[]>("/api/admin/registration-requests"),
        isAdmin ? request<typeof users>("/api/admin/users") : Promise.resolve([] as typeof users),
      ]);
      setRequests(registrationRequests);
      setUsers(activeUsers);
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const viewIdentityDocument = async (item: RegistrationReview) => {
    setError("");
    setBusy(item.id);
    try {
      const token = localStorage.getItem("vaulttrace_token");
      const response = await fetch(`${API}/api/admin/registration-requests/${item.id}/identity-document`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `The ID card image could not be loaded (${response.status})`);
      }
      const url = URL.createObjectURL(await response.blob());
      setIdentityDocumentPreview({ id: item.id, url });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  useEffect(() => { void load(); }, [role]);
  const decide = async (item: RegistrationReview, action: string) => {
    const reason = reasons[item.id]?.trim() || "";
    if (reason.length < 3) { setError("Enter a decision reason of at least 3 characters before taking action."); return; }
    setError(""); setBusy(item.id);
    try {
      await request(`/api/admin/registration-requests/${item.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ action, reason }),
      });
      setReasons((current) => ({ ...current, [item.id]: "" }));
      await load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const toggleUser = async () => {
    if (!userAction) return;
    const reason = userAction.reason.trim();
    if (reason.length < 3) {
      setError("Enter an audit reason of at least 3 characters.");
      return;
    }
    const target = users.find((item) => item.id === userAction.userId);
    if (!target) return;
    setBusy(target.id); setError("");
    try {
      await request(`/api/admin/users/${target.id}/activation`, {
        method: "PATCH",
        body: JSON.stringify({ active: userAction.active, reason }),
      });
      setUserAction(null);
      await load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  };
  const filteredRequests = requests.filter((item) => {
    if (registrationFilter === "needs_review" && ["approved", "rejected"].includes(item.status)) return false;
    if (registrationFilter !== "all" && registrationFilter !== "needs_review" && item.status !== registrationFilter) return false;
    const query = registrationSearch.trim().toLocaleLowerCase();
    if (!query) return true;
    return [item.full_name, item.username, item.email, item.registration_id, item.account_type, item.organization_name, item.institution_name, item.employee_id]
      .filter(Boolean).some((value) => value?.toLocaleLowerCase().includes(query));
  });
  const filteredUsers = users.filter((item) => {
    const query = userSearch.trim().toLocaleLowerCase();
    return !query || [item.username, item.email, item.role].filter(Boolean).some((value) => value?.toLocaleLowerCase().includes(query));
  });
  const pendingCount = requests.filter((item) => !["approved", "rejected"].includes(item.status)).length;
  const actionLabels: Record<string, string> = {
    verify_identity: "Verify identity",
    verify_employee: "Verify employee",
    verify_institution: "Approve institution association",
    approve_role: "Approve account",
    reject: "Reject request",
  };
  return <>
    <PageHeader eyebrow="ADMINISTRATION / ACCESS" title="Account approvals" description="Review applications, inspect submitted details and ID-card evidence, and record each decision." />
    <section className="panel account-approval-list">
      <div className="panel-heading account-section-heading"><div><h2>Registration requests</h2><p>{pendingCount} awaiting review · {requests.length} total</p></div><button className="button secondary" onClick={() => void load()} disabled={loading}>{loading ? "Refreshing…" : "Refresh requests"}</button></div>
      <div className="account-list-toolbar">
        <label htmlFor="registration-filter">Show<select id="registration-filter" value={registrationFilter} onChange={(event) => setRegistrationFilter(event.target.value)}><option value="needs_review">Awaiting review</option><option value="all">All requests</option><option value="pending_email_verification">Pending email</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label>
        <label htmlFor="registration-search">Find an applicant<input id="registration-search" type="search" value={registrationSearch} onChange={(event) => setRegistrationSearch(event.target.value)} placeholder="Name, username, email, institution or request ID" /></label>
      </div>
      {loadError && <div className="form-error" role="alert">{loadError}<button className="button ghost" onClick={() => void load()}>Try again</button></div>}
      {loading ? <div className="account-loading" role="status">Loading registration requests…</div> : requests.length === 0 ? <EmptyState text="No registration requests have been submitted yet." /> : filteredRequests.length === 0 ? <EmptyState text="No requests match these filters." /> : filteredRequests.map((item) => {
        const actions = item.status === "rejected" || item.status === "approved" ? [] : ["reject"];
        if (item.status !== "pending_email_verification") {
          if (item.identity_status === "pending") actions.push("verify_identity");
          if (item.employee_status === "pending") actions.push("verify_employee");
          if (item.institution_status === "pending") actions.push("verify_institution");
          if (isAdmin && item.identity_status === "approved" && ["approved", "not_required"].includes(item.employee_status) && ["approved", "not_required"].includes(item.institution_status) && item.role_status === "pending") actions.push("approve_role");
        }
        const progress = [
          ["Email", item.email_verified_at ? "verified" : "pending"],
          ["Identity", item.identity_status],
          ["Employee", item.employee_status],
          ["Institution", item.institution_status],
          ["Role", item.role_status],
        ];
        return <article className="account-request-card" key={item.id}>
          <div className="account-request-title">
            <div className="account-applicant">
              <span className="account-avatar" aria-hidden="true"><Icon name="user" size={18} /></span>
              <div><h3>{item.full_name}</h3><span>@{item.username} · {item.email}</span><small>Requested role: {item.account_type.replace(/_/g, " ")}</small></div>
            </div>
            <StatusBadge value={item.status} />
          </div>
          <div className="account-request-meta"><span>Request {item.registration_id}</span><span>Submitted {new Date(item.created_at).toLocaleString("en-IN")}</span></div>
          <details className="account-request-details">
            <summary>View submitted account details</summary>
            <dl className="account-details-grid">
              <dt>Full name</dt><dd>{item.full_name}</dd>
              <dt>Username</dt><dd>{item.username}</dd>
              <dt>Official email</dt><dd>{item.email}</dd>
              <dt>Requested account type</dt><dd>{item.account_type.replace(/_/g, " ")}</dd>
              <dt>Organization</dt><dd>{item.organization_name || "Not provided"}</dd>
              <dt>Institution association</dt><dd>{item.institution_name || (item.institution_id ? `Institution #${item.institution_id}` : "None requested")}</dd>
              <dt>Employee ID</dt><dd>{item.employee_id || "Not applicable"}</dd>
              <dt>Department</dt><dd>{item.department || "Not provided"}</dd>
              <dt>Designation</dt><dd>{item.designation || "Not provided"}</dd>
              <dt>Email verification</dt><dd>{item.email_verified_at ? `Verified ${new Date(item.email_verified_at).toLocaleString("en-IN")}` : "Pending"}</dd>
              <dt>Request reference</dt><dd>{item.registration_id}</dd>
              {item.decision_reason && <><dt>Latest decision</dt><dd>{item.decision_reason}{item.decision_at ? ` · ${new Date(item.decision_at).toLocaleString("en-IN")}` : ""}</dd></>}
            </dl>
          </details>
          <div className="identity-review-evidence">
            <div><b>Submitted ID card</b><span>{item.has_identity_document ? `Private image · ${item.identity_document_size ? `${(item.identity_document_size / (1024 * 1024)).toFixed(2)} MB` : "available"}` : "No image uploaded"}</span></div>
            {item.has_identity_document && (identityDocumentPreview?.id === item.id
              ? <button className="button secondary" onClick={() => setIdentityDocumentPreview(null)}>Close ID card</button>
              : <button className="button secondary" disabled={busy !== null} onClick={() => void viewIdentityDocument(item)}>{busy === item.id ? "Loading image…" : "View ID card"}</button>)}
            {identityDocumentPreview?.id === item.id && <div className="identity-review-preview"><img src={identityDocumentPreview.url} alt={`Submitted ID card for ${item.full_name}`} /><button className="button ghost" onClick={() => setIdentityDocumentPreview(null)}>Close image</button></div>}
          </div>
          <div className="approval-progress">{progress.map(([label, value]) => <div key={label} className={`approval-stage status-${value}`}><span>{label}</span><b>{value.replace(/_/g, " ")}</b></div>)}</div>
          {actions.length > 0 ? <div className="account-decision-controls">
            <label htmlFor={`decision-reason-${item.id}`}>Review notes <small>A reason is required for every action.</small><textarea id={`decision-reason-${item.id}`} rows={2} value={reasons[item.id] || ""} onChange={(e) => setReasons((current) => ({ ...current, [item.id]: e.target.value }))} placeholder="Add the review reason before choosing an action" required /></label>
            <div>{actions.map((action) => <button key={action} className={action === "reject" ? "button danger" : action === "approve_role" ? "button primary" : "button secondary"} disabled={busy !== null} onClick={() => void decide(item, action)}>{busy === item.id ? "Saving…" : actionLabels[action]}</button>)}</div>
          </div> : <div className="account-request-complete"><StatusBadge value={item.status} />{item.decision_reason && <span>{item.decision_reason}</span>}</div>}
        </article>;
      })}
    </section>
    {isAdmin && <details className="panel account-approval-list managed-accounts-panel">
      <summary className="managed-accounts-summary"><span><b>User accounts</b><small>{users.length} accounts · manage activation status</small></span><span>Manage accounts</span></summary>
      <label className="managed-user-search" htmlFor="managed-user-search">Find an account<input id="managed-user-search" type="search" value={userSearch} onChange={(event) => { setUserSearch(event.target.value); setVisibleUserLimit(20); }} placeholder="Username, email or role" /></label>
      {filteredUsers.length === 0 ? <EmptyState text={users.length ? "No accounts match your search." : "No active accounts found."} /> : filteredUsers.slice(0, visibleUserLimit).map((item) => <div className="managed-user-row" key={item.id}>
        <div className="managed-user-identity"><span className="account-avatar" aria-hidden="true">{item.username.slice(0, 1).toLocaleUpperCase()}</span><div><b>{item.username}</b><small>{item.email || "No email"} · {item.role.replace(/_/g, " ")}</small></div></div>
        <StatusBadge value={item.active ? "active" : "suspended"} />
        {userAction?.userId === item.id ? <div className="managed-user-confirm"><label htmlFor={`user-reason-${item.id}`}>{userAction.active ? "Reason for reactivation" : "Reason for suspension"}<textarea id={`user-reason-${item.id}`} rows={2} value={userAction.reason} onChange={(event) => setUserAction({ ...userAction, reason: event.target.value })} placeholder="Enter an audit reason (at least 3 characters)" required /></label><div><button className={userAction.active ? "button secondary" : "button danger"} disabled={busy !== null} onClick={() => void toggleUser()}>{busy === item.id ? "Saving…" : userAction.active ? "Confirm reactivation" : "Confirm suspension"}</button><button className="button ghost" onClick={() => setUserAction(null)}>Cancel</button></div></div> : <button className={item.active ? "button danger" : "button secondary"} disabled={busy !== null} onClick={() => setUserAction({ userId: item.id, active: !item.active, reason: "" })}>{item.active ? "Suspend" : "Reactivate"}</button>}
      </div>)}
      {filteredUsers.length > visibleUserLimit && <button className="button secondary" onClick={() => setVisibleUserLimit((limit) => limit + 20)}>Show more accounts ({filteredUsers.length - visibleUserLimit} remaining)</button>}
    </details>}
  </>;
}

function Overview({ setPage, setError }: { setPage: (p: Page) => void; setError: (s: string) => void }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [fdrs, setFdrs] = useState<Fdr[]>([]);
  const [directory, setDirectory] = useState<InstitutionSummary | null>(null);
  useEffect(() => { Promise.all([request<Summary>("/api/dashboard/summary"), request<Fdr[]>("/api/fdrs"), request<InstitutionSummary>("/api/institutions/summary")]).then(([s, f, d]) => { setSummary(s); setFdrs(f); setDirectory(d); }).catch((e) => setError(e.message)); }, [setError]);
  const statuses = useMemo(() => fdrs.reduce<Record<string, number>>((acc, item) => { acc[item.status] = (acc[item.status] || 0) + 1; return acc; }, {}), [fdrs]);
  return <><PageHeader eyebrow="OPERATIONS / OVERVIEW" title="Good morning, administrator" description="Here’s the current pulse of your deposit registry." action={<button className="button primary" onClick={() => setPage("registry")}><Icon name="plus" size={16} />Register an FDR</button>} /><section className="metric-grid">{[["institutions", "Institutions under management", "building", "neutral"], ["fdrs", "Registered instruments", "file", "blue"], ["verified", "Verified instruments", "shield", "teal"], ["pending", "Cases needing attention", "alert", "amber"]].map(([key, label, icon, tone]) => <div className="metric-card" key={key}><div className={`metric-icon ${tone}`}><Icon name={icon} /></div><div><span>{label}</span><strong>{summary?.[key as keyof Summary] ?? "—"}</strong><small>{key === "pending" ? "Review queue" : "Live database count"}</small></div></div>)}</section><section className="panel table-panel"><div className="panel-heading"><div><h2>Institution catalogue coverage</h2><p>AICTE directory data available for operational scenarios</p></div><button className="text-button" onClick={() => setPage("institutions")}>Explore directory <Icon name="arrow" size={15} /></button></div><div className="metric-grid"><div className="metric-card"><div className="metric-icon blue"><Icon name="building" /></div><div><span>Catalogue institutions</span><strong>{directory?.institutions ?? "—"}</strong><small>{directory?.states.length ?? 0} states / territories</small></div></div><div className="metric-card"><div className="metric-icon teal"><Icon name="list" /></div><div><span>Programme offerings</span><strong>{directory?.programmes ?? "—"}</strong><small>{directory?.institution_types.length ?? 0} institution types</small></div></div></div></section><div className="dashboard-grid"><section className="panel chart-panel"><div className="panel-heading"><div><h2>Registry health</h2><p>Current instrument status distribution</p></div><button className="text-button" onClick={() => setPage("registry")}>View registry <Icon name="arrow" size={15} /></button></div><div className="health-visual"><div className="donut" style={{ "--progress": `${Math.min(100, ((summary?.verified || 0) / Math.max(1, summary?.fdrs || 1)) * 100)}%` } as CSSProperties}><div><strong>{summary?.fdrs || 0}</strong><span>total FDRs</span></div></div><div className="legend">{Object.entries(statuses).length ? Object.entries(statuses).map(([status, count]) => <div key={status}><i className={`legend-dot dot-${status}`} /><span>{status.replace(/_/g, " ")}</span><b>{count}</b></div>) : <EmptyState text="No instruments have been registered yet." />}</div></div></section><section className="panel action-panel"><div className="panel-heading"><div><h2>Quick actions</h2><p>Move work forward</p></div></div><button onClick={() => setPage("institutions")}><span className="quick-icon blue"><Icon name="building" /></span><span><b>Review institutions</b><small>Manage directory records</small></span><Icon name="arrow" size={16} /></button><button onClick={() => setPage("verification")}><span className="quick-icon teal"><Icon name="shield" /></span><span><b>Open verification queue</b><small>{summary?.pending || 0} cases waiting</small></span><Icon name="arrow" size={16} /></button><button onClick={() => setPage("discrepancies")}><span className="quick-icon amber"><Icon name="alert" /></span><span><b>Resolve discrepancies</b><small>Keep the registry clean</small></span><Icon name="arrow" size={16} /></button></section></div><section className="panel table-panel"><div className="panel-heading"><div><h2>Recent instruments</h2><p>Latest records entering the registry</p></div><button className="text-button" onClick={() => setPage("registry")}>View all <Icon name="arrow" size={15} /></button></div><FdrTable rows={fdrs.slice(0, 5)} /></section></>;
}

function Institutions({ setError, role }: { setError: (s: string) => void; role: string }) {
  const [rows, setRows] = useState<Institution[]>([]); const [query, setQuery] = useState(""); const [state, setState] = useState(""); const [type, setType] = useState(""); const [page, setPage] = useState(1); const pageSize = 50; const [summary, setSummary] = useState<InstitutionSummary | null>(null); const [selected, setSelected] = useState<Institution | null>(null); const [programmes, setProgrammes] = useState<Programme[]>([]); const [showForm, setShowForm] = useState(false); const [loading, setLoading] = useState(true);
  const load = () => { setLoading(true); const params = new URLSearchParams({ q: query, page: String(page), page_size: String(pageSize) }); if (state) params.set("state", state); if (type) params.set("institution_type", type); request<Institution[]>(`/api/institutions?${params}`).then(setRows).catch((e) => setError(e.message)).finally(() => setLoading(false)); };
  useEffect(() => { request<InstitutionSummary>("/api/institutions/summary").then(setSummary).catch((e) => setError(e.message)); }, [setError]);
  useEffect(() => { load(); }, [query, state, type, page]);
  const open = (row: Institution) => { setSelected(row); request<Programme[]>(`/api/institutions/${row.id}/programmes`).then(setProgrammes).catch((e) => setError(e.message)); };
  return <><PageHeader eyebrow="DIRECTORY / INSTITUTIONS" title="Institution directory" description="Search the loaded AICTE catalogue by name, AICTE ID, state and type." action={["admin", "officer"].includes(role) ? <button className="button primary" onClick={() => setShowForm(true)}><Icon name="plus" size={16} />Add institution</button> : undefined} /><div className="toolbar"><div className="field-search"><Icon name="search" size={16} /><input placeholder="Search by name or identifier…" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1); }} /></div><select value={state} onChange={(e) => { setState(e.target.value); setPage(1); }}><option value="">All states</option>{summary?.states.map((item) => <option key={item} value={item}>{item}</option>)}</select><select value={type} onChange={(e) => { setType(e.target.value); setPage(1); }}><option value="">All institution types</option>{summary?.institution_types.map((item) => <option key={item} value={item}>{item}</option>)}</select><span className="result-count">{rows.length} shown · page {page}</span></div><section className="panel table-panel"><TableHeader title="AICTE institution catalogue" subtitle={`${summary?.programmes ?? "—"} programme records available`} /><table><thead><tr><th>Institution</th><th>Identifier</th><th>Location</th><th>Type</th><th className="align-right">Action</th></tr></thead><tbody>{loading ? <LoadingRows cols={5} /> : rows.length ? rows.map((row) => <tr key={row.id}><td><div className="entity-cell"><div className="entity-avatar">{row.name.slice(0, 1)}</div><div><b>{row.name}</b><small>{row.university || `Institution record #${row.id}`}</small></div></div></td><td><code>{row.aicte_id || row.code}</code></td><td className="muted">{[row.district, row.state].filter(Boolean).join(", ") || row.address || "Not provided"}</td><td>{row.institution_type || "—"}</td><td className="align-right"><button className="row-action" onClick={() => open(row)}>Open <Icon name="arrow" size={14} /></button></td></tr>) : <tr><td colSpan={5}><EmptyState text="No institutions found. Adjust the filters or add a directory record." /></td></tr>}  </tbody></table></section><div className="pagination-controls"><button className="button ghost" disabled={page === 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>Previous</button><span>Page {page}</span><button className="button ghost" disabled={loading || rows.length < pageSize} onClick={() => setPage((current) => current + 1)}>Next</button></div>{selected && <Modal title={selected.name} onClose={() => setSelected(null)}><p className="modal-intro">{selected.address || "Address not provided"}{selected.university ? ` · ${selected.university}` : ""}</p>  <div className="institution-facts"><div><b>AICTE ID</b><span>{selected.aicte_id || selected.code}</span></div><div><b>State / district</b><span>{[selected.state, selected.district].filter(Boolean).join(" / ") || "—"}</span></div><div><b>Institution type</b><span>{selected.institution_type || "—"}</span></div><div><b>Programme records</b><span>{programmes.length}</span></div></div><h3>Programmes and courses</h3><div className="programme-list">{programmes.length ? programmes.map((item) => <div className="programme-row" key={item.id}><div className="programme-level">{item.level || "Programme"}</div><div className="programme-content"><b>{item.course || item.programme}</b><small>{[item.programme, item.shift, item.availability].filter(Boolean).join(" · ")}{item.intake ? ` · Intake ${item.intake}` : ""}</small></div></div>) : <EmptyState text="No programme records found." />}</div></Modal>}{showForm && <InstitutionForm onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} setError={setError} />}</>;
}

function Registry({ setPage, setError, role, openInstrument }: { setPage: (p: Page) => void; setError: (s: string) => void; role: string; openInstrument: (id: number) => void }) {
  const [rows, setRows] = useState<Fdr[]>([]); const [institutions, setInstitutions] = useState<Institution[]>([]); const [query, setQuery] = useState(""); const [status, setStatus] = useState("all"); const [region, setRegion] = useState(""); const [bank, setBank] = useState(""); const [institutionQuery, setInstitutionQuery] = useState(""); const [fromDate, setFromDate] = useState(""); const [toDate, setToDate] = useState(""); const [belowL3, setBelowL3] = useState(false); const [hasFlags, setHasFlags] = useState(false); const [showForm, setShowForm] = useState(false);
  const load = () => request<Fdr[]>(`/api/fdrs?q=${encodeURIComponent(query)}`).then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); request<Institution[]>("/api/institutions").then(setInstitutions).catch((e) => setError(e.message)); }, [query]);
  const institutionName = (id: number) => institutions.find((item) => item.id === id);
  const banks = [...new Set(rows.map((row) => row.bank_name).filter(Boolean))] as string[];
  const regions = [...new Set(rows.map((row) => institutionName(row.institution_id)?.state).filter(Boolean))] as string[];
  const visible = rows.filter((row) => {
    const institution = institutionName(row.institution_id);
    const maturity = row.maturity_date.slice(0, 10);
    return (status === "all" || row.status === status) && (!region || institution?.state === region) && (!bank || row.bank_name === bank) && (!institutionQuery || `${institution?.name || ""} ${institution?.aicte_id || ""}`.toLowerCase().includes(institutionQuery.toLowerCase())) && (!fromDate || maturity >= fromDate) && (!toDate || maturity <= toDate) && (!belowL3 || row.status !== "verified") && (!hasFlags || false);
  });
  const risk = (row: Fdr) => row.status === "release_requested" || row.status === "submitted" ? "Medium 35" : row.status === "under_review" ? "High 55" : "Low 0";
  const riskClass = (row: Fdr) => risk(row).toLowerCase().split(" ")[0];
  const openInformation = (row: Fdr) => openInstrument(row.id);
  return <div className="instrument-page"><PageHeader eyebrow="WORKSPACE / FDR RECORDS" title="FDR records" description="Search and filter every FDR in your scope." action={["admin", "officer"].includes(role) ? <button className="button primary" onClick={() => setShowForm(true)}><Icon name="plus" size={16} />New submission</button> : undefined} /><section className="instrument-filters"><div className="instrument-search"><input placeholder='Ask in plain words, e.g. "expiring FDRs of Demo Union Bank in Western region"' value={query} onChange={(e) => setQuery(e.target.value)} /><button className="button primary">Search</button></div><div className="instrument-filter-row"><select value={status} onChange={(e) => setStatus(e.target.value)}><option value="all">Any status</option>{["draft", "submitted", "under_review", "verified", "release_requested", "approved", "closed"].map((item) => <option key={item} value={item}>{item.replace(/_/g, " ")}</option>)}</select><select value={region} onChange={(e) => setRegion(e.target.value)}><option value="">Any region</option>{regions.map((item) => <option key={item} value={item}>{item}</option>)}</select><select value={bank} onChange={(e) => setBank(e.target.value)}><option value="">Any bank</option>{banks.map((item) => <option key={item} value={item}>{item}</option>)}</select><input placeholder="Institution or AICTE ID" value={institutionQuery} onChange={(e) => setInstitutionQuery(e.target.value)} /><input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} /><input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} /></div><div className="instrument-checks"><label><input type="checkbox" checked={belowL3} onChange={(e) => setBelowL3(e.target.checked)} /> Below L3 (not bank-confirmed)</label><label><input type="checkbox" checked={hasFlags} onChange={(e) => setHasFlags(e.target.checked)} /> Has open flags</label></div></section><section className="panel table-panel instrument-table"><table><thead><tr><th>#</th><th>FDR no.</th><th>Institution</th><th>Bank</th><th>Amount</th><th>Maturity</th><th>Status</th>  <th>Verification</th><th>Flags</th><th>Risk</th><th>Information</th></tr></thead><tbody>{visible.length ? visible.map((row, index) => { const institution = institutionName(row.institution_id); return <tr key={row.id}><td>{index + 1}</td>    <td><button className="instrument-link" onClick={() => openInformation(row)}><code>{row.identifier}</code></button></td><td><b>{institution?.name || `Institution #${row.institution_id}`}</b><small className="table-sub">{institution?.code} · {institution?.state || "Region unavailable"}</small></td><td>{row.bank_name || "Bank pending"}</td><td>{formatAmount(row.amount)}</td><td>{new Date(row.maturity_date).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}</td><td><StatusBadge value={row.status} /></td><td><span className="verification-pill">L3 bank-confirmed</span></td><td className="muted">–</td>  <td><span className={`risk-pill ${riskClass(row)}`}>{risk(row)}</span></td><td><button className="row-action information-action" onClick={() => openInformation(row)}>Information <Icon name="arrow" size={14} /></button></td></tr>; }) : <tr><td colSpan={11}><EmptyState text="No FDR records match these filters." /></td></tr>}</tbody></table></section>{showForm && <FdrForm institutions={institutions} onClose={() => setShowForm(false)} onSaved={() => { setShowForm(false); load(); }} setError={setError} />}</div>;
}

function InstrumentDetail({ id, setPage, setError, role }: { id: number; setPage: (p: Page) => void; setError: (s: string) => void; role: string }) {
  const [fdr, setFdr] = useState<Fdr | null>(null);
  const [institution, setInstitution] = useState<Institution | null>(null);
  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [versions, setVersions] = useState<VersionRow[]>([]);
  const [timeline, setTimeline] = useState<TimelineRow[]>([]);
  const [custody, setCustody] = useState<CustodyRow[]>([]);
  const [flags, setFlags] = useState<Discrepancy[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [cases, setCases] = useState<ReleaseRow[]>([]);
  const [upload, setUpload] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState("");

  useEffect(() => {
    Promise.all([
      request<Fdr[]>("/api/fdrs"),
      request<Institution[]>("/api/institutions"),
      request<DocumentRow[]>(`/api/fdrs/${id}/documents`),
      request<VersionRow[]>(`/api/fdrs/${id}/versions`),
      request<TimelineRow[]>(`/api/fdrs/${id}/timeline`),
      request<CustodyRow[]>(`/api/fdrs/${id}/custody`),
      request<Discrepancy[]>(`/api/fdrs/${id}/discrepancies`),
      request<AuditRow[]>(`/api/fdrs/${id}/audit`),
      request<ReleaseRow[]>(`/api/fdrs/${id}/release-requests`),
    ]).then(([fdrs, institutions, docs, versionRows, timelineRows, custodyRows, flagRows, auditRows, releaseRows]) => {
      const selected = fdrs.find((item) => item.id === id) || null;
      setFdr(selected);
      setInstitution(institutions.find((item) => item.id === selected?.institution_id) || null);
      setDocuments(docs);
      setVersions(versionRows);
      setTimeline(timelineRows);
      setCustody(custodyRows);
      setFlags(flagRows);
      setAudit(auditRows);
      setCases(releaseRows);
    }).catch((e) => setError(e.message));
  }, [id, setError]);

  if (!fdr) return <div className="loading-screen"><span>Loading instrument...</span></div>;
  const risk = fdr.status === "under_review" ? "High 55" : fdr.status === "submitted" || fdr.status === "release_requested" ? "Medium 35" : "Low 0";
  const empty = (text: string) => <div className="detail-empty">{text}</div>;
  const runOcr = async (documentId: number) => {
    try {
      const result = await request<{ provider: string; text: string }>(`/api/documents/${documentId}/extract`, { method: "POST" });
      alert(`${result.provider} completed: ${result.text.length} characters. Authenticity remains unconfirmed.`);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const uploadDocument = async () => {
    if (!upload) return;
    const form = new FormData();
    form.append("file", upload);
    try {
      const result = await request<{ id: number; sha256: string }>(`/api/fdrs/${id}/documents`, { method: "POST", body: form });
      setDocuments((current) => [...current, { id: result.id, fdr_id: id, original_name: upload.name, sha256: result.sha256, content_type: upload.type, size: upload.size, created_at: new Date().toISOString() }]);
      setUpload(null);
      setUploadMessage("Document uploaded securely.");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const fields = [["FDR number", fdr.identifier], ["Issuing bank", fdr.bank_name || "Not provided"], ["Amount", formatAmount(fdr.amount)], ["Issue date", fdr.issue_date ? new Date(fdr.issue_date).toLocaleDateString("en-IN") : "Not provided"], ["Maturity date", new Date(fdr.maturity_date).toLocaleDateString("en-IN")]];
  return <div className="instrument-detail">
    <button className="back-link" onClick={() => setPage("registry")}>← Back to FDR records</button>
    <div className="detail-heading"><div><h1>FDR record #{fdr.id} {fdr.identifier}</h1><p>{institution?.name || "Institution"} · {institution?.state || "Region unavailable"} · AICTE ID {institution?.aicte_id || institution?.code}</p></div><div className="detail-badges"><StatusBadge value={fdr.status} /><span className="verification-pill">L3 bank-confirmed</span><span className="risk-pill low">{risk}</span></div></div>
    <div className="detail-actions"><button className="button secondary" disabled={!["admin", "officer"].includes(role)}>Submit renewal</button><button className="button secondary" onClick={() => setPage("release")}>Request release / discharge / refund</button></div>
    <div className="detail-grid">
      <section className="panel detail-card detail-wide"><h2>Fields and provenance</h2><div className="provenance-table"><div className="provenance-head"><span>Field</span><span>Value</span><span>Source</span></div>{fields.map(([label, value]) => <div className="provenance-row" key={label}><span>{label}</span><b>{value}</b><span className="verification-pill">Bank-confirmed</span></div>)}</div><p className="detail-note">Version {versions.length || 1} of {versions.length || 1}. Custody: {custody[0]?.location || "Not recorded"}. In favour of: {fdr.beneficiary || "Not provided"}. Lien marked: {fdr.lien_endorsed ? "yes" : "no"}.</p></section>
      <section className="panel detail-card"><h2>Risk score <span className="score">0/100</span></h2>{empty("No risk factors")}<p className="detail-note">Renewal deadline not configured<br />Maturity date {new Date(fdr.maturity_date).toLocaleDateString("en-IN")}</p></section>
      <section className="panel detail-card detail-wide"><h2>Documents <span className="card-caption">SHA-256 fingerprint per version</span></h2>{documents.length ? <div className="document-list">{documents.map((doc) => <div className="document-row" key={doc.id}><span>{doc.content_type === "application/pdf" ? "FDR SCAN" : "EVIDENCE"}</span><span>1</span><a href={`${API}/api/documents/${doc.id}/download`} target="_blank" rel="noreferrer">{doc.original_name}</a><code>{doc.sha256.slice(0, 16)}...</code><span>{new Date(doc.created_at).toLocaleString("en-IN")}</span><button className="button ghost" onClick={() => runOcr(doc.id)}>Run OCR</button></div>)}</div> : empty("No documents uploaded")}<div className="detail-upload"><label>Add FDR scan<input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setUpload(e.target.files?.[0] || null)} /></label><button className="button secondary" disabled={!upload || !["admin", "officer"].includes(role)} onClick={uploadDocument}>Upload document</button>{uploadMessage && <span className="success-message">{uploadMessage}</span>}</div></section>
      <section className="panel detail-card"><h2>Flags</h2>{flags.length ? flags.map((flag) => <p key={flag.id}>{flag.severity}: {flag.explanation}</p>) : empty("No flags")}</section>
      <section className="panel detail-card"><h2>Bank verification</h2>{empty("No request sent")}<p className="detail-note">The bank is simulated for this prototype. No real bank is contacted.</p></section>
      <section className="panel detail-card"><h2>Observations</h2>{empty("None yet")}</section>
      <section className="panel detail-card"><h2>Physical custody</h2>{custody.length ? custody.map((event) => <p key={event.id}>{event.event_type} · {event.location} · {event.custodian}</p>) : empty("No custody events")}</section>
      <section className="panel detail-card"><h2>Versions and renewals</h2>{versions.length ? <div className="mini-list">{versions.map((version) => <div key={version.id}><span>{version.version_number}</span><b>{fdr.identifier}</b><span>{formatAmount(fdr.amount)}</span><span>{new Date(fdr.maturity_date).toLocaleDateString("en-IN")}</span><span>{new Date(version.created_at).toLocaleString("en-IN")}</span></div>)}</div> : empty("No versions recorded")}</section>
      <section className="panel detail-card"><h2>Cases</h2>{cases.length ? cases.map((item) => <p key={item.id}><b>{item.request_type}</b> · {item.status}<br /><small>{item.reason}</small></p>) : empty("No release cases")}</section>
      <section className="panel detail-card detail-wide"><h2>Timeline <span className="card-caption">Audit trail for this instrument</span></h2>{audit.length ? <div className="timeline-list">{audit.map((event) => <div key={event.id}><time>{new Date(event.created_at).toLocaleString("en-IN")}</time><b>{event.action}</b><span>{event.details || "No additional detail"}</span></div>)}</div> : timeline.length ? <div className="timeline-list">{timeline.map((event) => <div key={event.id}><time>{new Date(event.created_at).toLocaleString("en-IN")}</time><b>{event.from_status || "created"} → {event.to_status}</b><span>{event.reason || "Lifecycle update"}</span></div>)}</div> : empty("No lifecycle events")}</section>
    </div>
  </div>;
}

function Verification({ setPage, setError, openDiscrepancy }: { setPage: (p: Page) => void; setError: (s: string) => void; openDiscrepancy: (id: number) => void }) {
  const [rows, setRows] = useState<Fdr[]>([]); useEffect(() => { request<Fdr[]>("/api/fdrs").then(setRows).catch((e) => setError(e.message)); }, [setError]);
  const queue = rows.filter((row) => ["submitted", "under_review"].includes(row.status));
  return <><PageHeader eyebrow="OPERATIONS / VERIFICATION" title="Verification centre" description="Review evidence, record outcomes and keep authenticity decisions separate from OCR." action={<button className="button secondary" onClick={() => setPage("documents")}><Icon name="paperclip" size={16} />Review documents</button>} /><div className="info-banner"><Icon name="shield" size={18} /><div><b>Evidence-led verification</b><span>OCR and document hashes support review but do not prove authenticity or bank confirmation.</span></div></div><section className="panel table-panel"><TableHeader title="Cases awaiting review" subtitle={`${queue.length} cases in your queue`} /><table><thead><tr><th>Instrument</th><th>Holder</th><th>Amount</th><th>Due date</th><th>Status</th><th /></tr></thead><tbody>{queue.length ? queue.map((row) => <tr key={row.id}><td><b>{row.identifier}</b><small className="table-sub">FDR-{String(row.id).padStart(5, "0")}</small></td><td>{row.holder_name}</td><td>{formatAmount(row.amount)}</td><td>{new Date(row.maturity_date).toLocaleDateString("en-IN")}</td><td><StatusBadge value={row.status} /></td><td className="align-right"><button className="row-action" onClick={() => openDiscrepancy(row.id)}>Open case <Icon name="arrow" size={14} /></button></td></tr>) : <tr><td colSpan={6}><EmptyState text="Your verification queue is clear." /></td></tr>}</tbody></table></section></>;
}

function Documents({ setError, setPage }: { setError: (s: string) => void; setPage: (page: Page) => void }) {
  const [fdrs, setFdrs] = useState<Fdr[]>([]); const [institutions, setInstitutions] = useState<Institution[]>([]); const [selected, setSelected] = useState(""); const [file, setFile] = useState<File | null>(null); const [message, setMessage] = useState(""); const [processing, setProcessing] = useState(false); const [extracted, setExtracted] = useState<{ id: number; document_id: number; provider: string; text: string; page_count: number; authenticity_confirmed: boolean } | null>(null); const [draftValues, setDraftValues] = useState<FdrDraftValues>({}); const [showRegistration, setShowRegistration] = useState(false);
  useEffect(() => { Promise.all([request<Fdr[]>("/api/fdrs"), request<Institution[]>("/api/institutions")]).then(([rows, directory]) => { setFdrs(rows); const known = new Set(directory.map((item) => item.id)); const fallbacks = rows.filter((row) => !known.has(row.institution_id)).map((row) => ({ id: row.institution_id, name: row.joint_holder || row.holder_name || `Institution #${row.institution_id}`, code: `FDR-${row.institution_id}`, address: "", district: "", state: "", institution_type: "", women: "", minority: "", university: "" })); setInstitutions([...directory, ...fallbacks]); }).catch((e) => setError(e.message)); }, [setError]);
  const chooseFile = (candidate: File | null) => { if (!candidate) return; if (candidate.size > 10 * 1024 * 1024) { setError("The document must be smaller than 10 MB."); return; } setFile(candidate); setMessage(""); setExtracted(null); };
  const analyze = async () => { if (!file) { setError("Choose an FDR document first."); return; } const target = selected || fdrs[0]?.id?.toString(); if (!target) { setError("Create or select an FDR record before attaching a document."); return; } const form = new FormData(); form.append("file", file); setProcessing(true); setMessage("Uploading document and running OCR…"); try { const result = await request<{ id: number; sha256: string }>(`/api/fdrs/${target}/documents`, { method: "POST", body: form }); const extraction = await request<{ id: number; document_id: number; provider: string; text: string; page_count: number; authenticity_confirmed: boolean }>(`/api/documents/${result.id}/extract`, { method: "POST" }); setExtracted(extraction); setMessage(`Document analyzed with ${extraction.provider}. Candidate fields are ready for review.`); setSelected(target); } catch (e) { setMessage(""); setError((e as Error).message); } finally { setProcessing(false); } };
  const onDrop = (event: DragEvent<HTMLLabelElement>) => { event.preventDefault(); chooseFile(event.dataTransfer.files[0] || null); };
  const convertToDraft = async () => { if (!extracted) return; setProcessing(true); setMessage("Converting extraction into FDR form fields…"); try { const result = await request<{ fields: FdrDraftValues }>(`/api/documents/${extracted.document_id}/convert-to-fdr-draft?fdr_id=${encodeURIComponent(selected || "")}`, { method: "POST" }); setDraftValues(result.fields); setShowRegistration(true); setMessage("Candidate fields loaded into the FDR master-record form. Review them before submitting."); } catch (e) { setError((e as Error).message); } finally { setProcessing(false); } };
  return <><PageHeader eyebrow="MAIN WORKFLOW / INTAKE" title="Upload & Analyze FDR" description="Upload a fixed deposit receipt and convert its document evidence into a reviewable FDR master-record draft." /><div className="local-demo-banner"><Icon name="shield" size={16} /><b>Local processing & privacy assurance</b><span>OCR and text parsing run through the configured local provider. Authenticity and bank confirmation still require review.</span></div><section className="analyze-layout"><div className="panel analyze-card"><div className="eyebrow">AUTO OCR</div><h2>Upload your FDR document</h2><p>Upload a Fixed Deposit Receipt or Security Deposit document. The system extracts candidate financial terms and validates the input before it enters the FDR repository.</p><label className="analyze-dropzone" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}><input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => chooseFile(e.target.files?.[0] || null)} /><Icon name="upload" size={28} /><b>{file ? file.name : "Drag and drop your FDR document here, or"}</b><button type="button" className="button primary">Choose FDR document</button><small>Supported formats: JPG, JPEG, PNG, PDF · Max size: 10 MB</small></label><label className="select-label">Attach to existing FDR record (optional)<select value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">Use first available record</option>{fdrs.map((row) => <option value={row.id} key={row.id}>{row.identifier} · {row.holder_name}</option>)}</select></label><button className="button primary wide" disabled={processing} onClick={analyze}><Icon name="upload" size={16} />{processing ? "Uploading and processing…" : "Analyze document"}</button>{message && <div className="success-message"><Icon name={processing ? "clock" : "check"} size={15} />{message}</div>}</div><div className="panel analyze-guidance"><div className="eyebrow">CONVERSION FLOW</div><h2>Manual document → FDR repository</h2><div className="conversion-steps"><div><i>1</i><span><b>Upload</b><small>Store the original and SHA-256 fingerprint</small></span></div><div><i>2</i><span><b>Extract</b><small>Run PyMuPDF or Tesseract OCR</small></span></div><div><i>3</i><span><b>Review</b><small>Check candidate fields against the document</small></span></div><div><i>4</i><span><b>Register</b><small>Submit a draft into the FDR master records</small></span></div></div><button className="button secondary wide" onClick={() => setPage("registry")}>Open FDR master records <Icon name="arrow" size={16} /></button></div></section>{extracted && <section className="panel extraction-review"><div><div className="eyebrow">EXTRACTION RESULT</div><h2>Review candidate data before registration</h2><p>{extracted.provider} · {extracted.page_count} page(s) · {extracted.text.length} characters · authenticity unconfirmed</p></div><div className="extracted-text">{extracted.text || "No text was detected. Use the original document and enter values manually."}</div><div className="form-actions"><button className="button ghost" onClick={() => setExtracted(null)}>Discard result</button><button className="button primary" disabled={processing} onClick={convertToDraft}>{processing ? "Converting…" : "Convert to FDR master-record draft"} <Icon name="arrow" size={16} /></button></div></section>}{showRegistration && <FdrForm institutions={institutions} initialValues={draftValues} sourceDocumentId={extracted?.document_id} onClose={() => setShowRegistration(false)} onSaved={(result) => { setShowRegistration(false); setMessage(result ? `Submitted as incomplete intake draft #${result.intake_id}; it is saved for review.` : "FDR draft created in the master records."); if (!result) setPage("registry"); }} setError={setError} />}</>;
}

function Discrepancies({ setError, initialFdrId, onSelectFdr, role }: { setError: (s: string) => void; initialFdrId: number | null; onSelectFdr: (id: number | null) => void; role: string }) {
  const [fdrs, setFdrs] = useState<Fdr[]>([]);
  const [rows, setRows] = useState<Discrepancy[]>([]);
  const [selected, setSelected] = useState(initialFdrId ? String(initialFdrId) : "");
  const [loading, setLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [analysisMethod, setAnalysisMethod] = useState("");
  const [reviewNotes, setReviewNotes] = useState<Record<number, string>>({});
  const [savingFinding, setSavingFinding] = useState<number | null>(null);
  const autoAnalyzedFdrId = useRef<number | null>(null);
  const analysisRequestId = useRef(0);
  const [chatMessages, setChatMessages] = useState<DiscrepancyChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");

  const load = async (id: string) => {
    const requestId = ++analysisRequestId.current;
    setSelected(id);
    onSelectFdr(id ? Number(id) : null);
    setRows([]);
    setAnalysisError("");
    setAnalysisMethod("");
    setChatMessages([]);
    setChatInput("");
    setChatError("");
    if (!id) {
      autoAnalyzedFdrId.current = null;
      setLoading(false);
      return;
    }
    autoAnalyzedFdrId.current = Number(id);
    setLoading(true);
    try {
      const result = await request<{ fdr_id: number; analysis_method: string; findings: Discrepancy[] }>(`/api/fdrs/${id}/discrepancies/analyze`, { method: "POST" });
      if (requestId === analysisRequestId.current) {
        setRows(result.findings);
        setAnalysisMethod(result.analysis_method);
      }
    } catch (e) {
      if (requestId === analysisRequestId.current) setAnalysisError((e as Error).message);
    } finally {
      if (requestId === analysisRequestId.current) setLoading(false);
    }
  };

  const reload = async (id: string, requestId: number) => {
    const findings = await request<Discrepancy[]>(`/api/fdrs/${id}/discrepancies`);
    if (requestId === analysisRequestId.current && id === selected) {
      setRows(findings);
    }
  };

  const downloadEvidence = async (documentId: number) => {
    try {
      const token = localStorage.getItem("vaulttrace_token");
      const response = await fetch(`${API}/api/documents/${documentId}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error(`Evidence download failed (${response.status})`);
      const blobUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      const disposition = response.headers.get("content-disposition") || "";
      const extension = response.headers.get("content-type") === "application/pdf"
        ? ".pdf"
        : response.headers.get("content-type") === "image/png" ? ".png" : ".jpg";
      anchor.href = blobUrl;
      anchor.download = disposition.match(/filename="?([^";]+)"?/i)?.[1] || `vaulttrace-document-${documentId}${extension}`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
    } catch (e) {
      setAnalysisError((e as Error).message);
    }
  };

  useEffect(() => {
    request<Fdr[]>("/api/fdrs").then(setFdrs).catch((e) => setError(e.message));
  }, [setError]);

  useEffect(() => {
    if (initialFdrId && autoAnalyzedFdrId.current !== initialFdrId) {
      void load(String(initialFdrId));
    } else if (!initialFdrId) {
      autoAnalyzedFdrId.current = null;
    }
  }, [initialFdrId]);

  const review = async (finding: Discrepancy, action: string) => {
    const reason = reviewNotes[finding.id]?.trim() || "";
    if (reason.length < 3) {
      setAnalysisError("Enter a short reason or review note before recording this action.");
      return;
    }
    setSavingFinding(finding.id);
    setAnalysisError("");
    const requestId = analysisRequestId.current;
    try {
      await request(`/api/discrepancies/${finding.id}/review`, {
        method: "POST",
        body: JSON.stringify({ action, reason }),
      });
      if (requestId === analysisRequestId.current) await reload(selected, requestId);
      setReviewNotes((current) => ({ ...current, [finding.id]: "" }));
    } catch (e) {
      if (requestId === analysisRequestId.current) setAnalysisError((e as Error).message);
    } finally {
      setSavingFinding(null);
    }
  };

  const askAssistant = async (question = chatInput) => {
    const prompt = question.trim();
    if (!selected || prompt.length < 2 || chatLoading || loading) return;
    setChatInput("");
    setChatError("");
    setChatLoading(true);
    setChatMessages((current) => [...current, { role: "user", text: prompt }]);
    try {
      const result = await request<{ fdr_id: number; analysis_method: string; reply: string; sources: string[] }>(
        `/api/fdrs/${selected}/discrepancies/chat`,
        { method: "POST", body: JSON.stringify({ question: prompt }) },
      );
      if (result.fdr_id !== Number(selected)) throw new Error("The assistant returned a result for a different instrument.");
      setChatMessages((current) => [...current, { role: "assistant", text: result.reply, sources: result.sources }]);
    } catch (e) {
      setChatError((e as Error).message);
    } finally {
      setChatLoading(false);
    }
  };

  const selectedFdr = fdrs.find((row) => String(row.id) === selected);
  const openCount = rows.filter((row) => row.status === "open" && row.review_status !== "dismissed").length;
  const seriousCount = rows.filter((row) => ["critical", "high"].includes(row.severity.toLowerCase())).length;
  const awaitingCount = rows.filter((row) => ["pending", "evidence_requested", "escalated"].includes(row.review_status || "pending")).length;
  const canReview = ["admin", "reviewer"].includes(role);
  const actions = [
    ["mark_reviewed", "Mark reviewed"],
    ["confirm", "Confirm"],
    ["dismiss", "Dismiss"],
    ["request_evidence", "Request evidence"],
    ["escalate", "Escalate"],
    ["add_note", "Add note"],
  ];

  return <>
    <PageHeader eyebrow="OPERATIONS / CONTROL" title="Discrepancy centre" description="Explainable findings that prompt review—not automatic fraud labels." />
    <div className="discrepancy-metrics">
      <div className="metric-card"><div className="metric-icon amber"><Icon name="alert" size={18} /></div><div><span>Open findings</span><strong>{selected ? openCount : "—"}</strong><small>{selected ? "For selected instrument" : "Select an instrument to inspect"}</small></div></div>
      <div className="metric-card"><div className="metric-icon blue"><Icon name="alert" size={18} /></div><div><span>Critical / high</span><strong>{selected ? seriousCount : "—"}</strong><small>Findings requiring careful review</small></div></div>
      <div className="metric-card"><div className="metric-icon teal"><Icon name="clock" size={18} /></div><div><span>Awaiting reviewer action</span><strong>{selected ? awaitingCount : "—"}</strong><small>Pending, evidence request or escalation</small></div></div>
      <div className="metric-card"><div className="metric-icon neutral"><Icon name="shield" size={18} /></div><div><span>Analysis method</span><strong>{selected ? analysisMethod.replace(/_/g, " ") || "—" : "—"}</strong><small>Findings are recommendations, not authenticity proof</small></div></div>
    </div>
    <div className="toolbar"><div className="field-search"><Icon name="search" size={16} /><select value={selected} onChange={(e) => void load(e.target.value)}><option value="">Select an instrument to inspect…</option>{fdrs.map((row) => <option value={row.id} key={row.id}>{row.identifier} · {row.holder_name}</option>)}</select></div></div>
    {selectedFdr && <div className="info-banner"><Icon name="file" size={18} /><div><b>{selectedFdr.identifier} · {selectedFdr.holder_name}</b><span>FDR record #{selectedFdr.id} · {formatAmount(selectedFdr.amount)} · Maturity {new Date(selectedFdr.maturity_date).toLocaleDateString("en-IN")}. Findings below are limited to this instrument.</span></div></div>}
    <section className="panel analysis-chat" aria-label="Ask about this instrument">
      <div className="analysis-chat-heading"><div><div className="eyebrow">VAULTTRACE REVIEW ASSISTANT</div><h2>Ask about this instrument</h2><p>Ask in plain language about findings, amounts, dates, evidence or next steps.</p></div><span className="analysis-method-pill">Rule-based · source-grounded</span></div>
      <div className="analysis-chat-notice">This chat uses only records and findings available to your account. Replies are rule-based, not generated by an external AI, and do not confirm authenticity.</div>
      <div className="analysis-chat-transcript" aria-live="polite">
        {!selected && <div className="chat-empty">Select an FDR above to ask questions about its available records.</div>}
        {selected && !chatMessages.length && <div className="chat-welcome"><b>What would you like to review?</b><span>I can summarize the selected instrument’s findings and explain which available records support them.</span></div>}
        {chatMessages.map((message, index) => <div className={`chat-message chat-${message.role}`} key={`${index}-${message.role}`}><span className="chat-avatar">{message.role === "assistant" ? "V" : "You"}</span><div className="chat-message-content"><div>{message.text}</div>{message.sources?.length ? <div className="chat-sources"><b>Sources</b>{message.sources.map((source) => <span key={source}>{source}</span>)}</div> : null}</div></div>)}
        {chatLoading && <div className="chat-working" role="status">Checking this FDR’s available records…</div>}
      </div>
      {chatError && <div className="analysis-error" role="alert">{chatError}</div>}
      <div className="chat-suggestions">{["Summarize the findings", "Does the amount match?", "What evidence is missing?", "What should I review next?"].map((suggestion) => <button className="button ghost" key={suggestion} disabled={!selected || loading || chatLoading} onClick={() => void askAssistant(suggestion)}>{suggestion}</button>)}</div>
      <form className="analysis-chat-form" onSubmit={(event) => { event.preventDefault(); void askAssistant(); }}>
        <label className="sr-only" htmlFor="discrepancy-chat-question">Ask a question about this FDR</label>
        <input id="discrepancy-chat-question" value={chatInput} onChange={(event) => setChatInput(event.target.value)} maxLength={500} disabled={!selected || loading || chatLoading} placeholder={selected ? "Ask about the findings or evidence…" : "Select an instrument first"} />
        <button className="button primary" disabled={!selected || loading || chatLoading || chatInput.trim().length < 2}>{chatLoading ? "Checking…" : "Ask"}<Icon name="arrow" size={15} /></button>
      </form>
    </section>
    <section className="discrepancy-guidance"><div><b>How to review a finding</b><span>Compare the expected and observed values, inspect the cited records, then record a reasoned decision.</span></div><div><b>Severity is explainable</b><span>Findings identify a mismatch for review. They do not automatically label an institution as fraudulent.</span></div><div><b>Evidence remains separate</b><span>OCR and document hashes support review but do not prove authenticity or bank confirmation.</span></div></section>
    <section className="panel table-panel">
      <TableHeader title="Findings" subtitle={selected ? `${rows.length} findings attached to selected instrument` : "Select an instrument to load findings"} />
      {loading ? <EmptyState text="Analyzing available records for this instrument…" /> : analysisError ? <div className="analysis-error" role="alert">{analysisError}</div> : rows.length ? rows.map((row) => <article className="finding" key={row.id}>
        <div className={`severity severity-${row.severity.toLowerCase()}`}>{row.severity}</div>
        <div className="finding-body">
          <div className="finding-title"><b>{row.title || row.rule_id}</b><StatusBadge value={row.review_status || row.status} /></div>
          <p>{row.explanation}</p>
          {row.affected_field && <p><b>Affected field:</b> {row.affected_field}</p>}
          <div className="finding-comparison">
            <div><small>Expected {row.expected_source ? `· ${row.expected_source}` : ""}</small><b>{row.expected_value || "Not available"}</b></div>
            <div><small>Observed {row.observed_source ? `· ${row.observed_source}` : ""}</small><b>{row.observed_value || "Not available"}</b></div>
          </div>
          {row.evidence_reference && <div className="finding-reference"><b>Supporting evidence:</b> {row.evidence_reference}{row.evidence_document_ids?.map((documentId) => <button className="button ghost evidence-download" key={documentId} onClick={() => void downloadEvidence(documentId)}>Open document #{documentId}</button>)}</div>}
          {row.recommended_action && <p className="finding-action"><b>Recommended action:</b> {row.recommended_action}</p>}
          {row.history?.length ? <details className="finding-history"><summary>Review history ({row.history.length})</summary>{row.history.map((event) => <div key={event.id}><b>{event.action.replace(/_/g, " ")}</b><span>{event.reason}</span><small>Reviewer #{event.actor_id} · {new Date(event.created_at).toLocaleString("en-IN")}</small></div>)}</details> : null}
          {canReview && <div className="finding-review"><label>Reviewer note or decision reason<textarea value={reviewNotes[row.id] || ""} onChange={(event) => setReviewNotes((current) => ({ ...current, [row.id]: event.target.value }))} placeholder="Record the evidence-based reason for your action" /></label><div className="finding-review-actions">{actions.map(([action, label]) => <button className="button secondary" key={action} disabled={savingFinding === row.id || (reviewNotes[row.id] || "").trim().length < 3} onClick={() => void review(row, action)}>{savingFinding === row.id ? "Saving…" : label}</button>)}</div></div>}
        </div>
      </article>) : selected ? <EmptyState text="No discrepancies were detected in the available records. This does not establish the instrument’s authenticity." /> : <EmptyState text="Choose an instrument above to inspect its findings." />}
    </section>
  </>;
}

function Release({ setError, role }: { setError: (s: string) => void; role: string }) {
  const [fdrs, setFdrs] = useState<Fdr[]>([]); const [cases, setCases] = useState<ReleaseRow[]>([]); const [selected, setSelected] = useState(""); const [reason, setReason] = useState(""); const [type, setType] = useState("release"); const [decisionNotes, setDecisionNotes] = useState(""); const [evidence, setEvidence] = useState(""); const [message, setMessage] = useState("");
  const load = () => Promise.all([request<Fdr[]>("/api/fdrs"), request<ReleaseRow[]>("/api/release-requests")]).then(([instruments, releaseCases]) => { setFdrs(instruments); setCases(releaseCases); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);
  const activeCase = cases.find((item) => String(item.fdr_id) === selected) || cases[0];
  const instrument = fdrs.find((item) => item.id === Number(activeCase?.fdr_id));
  const submit = async () => { try { await request(`/api/fdrs/${selected}/release-requests`, { method: "POST", body: JSON.stringify({ request_type: type, reason }) }); setMessage("Case created and queued for independent review."); setReason(""); load(); } catch (e) { setError((e as Error).message); } };
  const decide = async (approved: boolean) => { if (!activeCase) return; try { await request(`/api/release-requests/${activeCase.id}/decision`, { method: "PATCH", body: JSON.stringify({ approved, decision_notes: decisionNotes }) }); setMessage(approved ? "Case approved for execution." : "Case rejected with an audit note."); setDecisionNotes(""); load(); } catch (e) { setError((e as Error).message); } };
  const execute = async () => { if (!activeCase) return; try { await request(`/api/release-requests/${activeCase.id}/execute`, { method: "POST", body: JSON.stringify({ evidence_reference: evidence, execution_notes: decisionNotes || "Physical release recorded." }) }); setMessage("Execution recorded. Independent closure is still required."); setEvidence(""); load(); } catch (e) { setError((e as Error).message); } };
  const close = async () => { if (!activeCase) return; try { await request(`/api/release-requests/${activeCase.id}/close`, { method: "POST", body: JSON.stringify({ evidence_reference: evidence, execution_notes: decisionNotes || "Case closure recorded." }) }); setMessage("Release case closed."); setEvidence(""); load(); } catch (e) { setError((e as Error).message); } };
  const stages = ["REQUESTED", "COMPLETENESS CHECK", "RO VERIFICATION", "PARALLEL CLEARANCE", "COMPETENT AUTHORITY", "NOC ISSUED", "ORIGINAL RETURNED", "CLOSED"];
  const stageIndex = !activeCase ? 0 : activeCase.status === "pending" ? 2 : activeCase.status === "approved" ? 5 : activeCase.status === "executed" ? 7 : activeCase.status === "closed" ? 8 : 1;
  return <><PageHeader eyebrow="LIFECYCLE / CONTROLLED ACTIONS" title="Release cases" description="Governed release, discharge and refund workflow with independent approvals." action={<button className="button primary" onClick={() => document.getElementById("new-release-case")?.scrollIntoView({ behavior: "smooth" })}><Icon name="plus" size={16} />New case</button>} /><div className="release-case-picker"><label>Open case<select value={activeCase?.id || ""} onChange={(e) => { const selectedCase = cases.find((item) => String(item.id) === e.target.value); setSelected(selectedCase ? String(selectedCase.fdr_id) : ""); }}><option value="">Select a release case…</option>{cases.map((item) => <option value={item.id} key={item.id}>Case #{item.id} · {item.request_type} · {item.status}</option>)}</select></label></div>{activeCase && <><div className="release-case-heading"><div><h2>Case #{activeCase.id}: {activeCase.request_type.toUpperCase()}</h2><p>{instrument?.identifier || `FDR #${activeCase.fdr_id}`} · {formatAmount(instrument?.amount || 0)}</p></div><StatusBadge value={activeCase.status} /></div><div className="release-flow">{stages.map((stage, index) => <div className={index < stageIndex ? "flow-step complete" : index === stageIndex ? "flow-step current" : "flow-step"} key={stage}><span>{stage}</span>{index < stages.length - 1 && <b>›</b>}</div>)}</div><div className="release-layout"><section className="panel release-guards"><h2>Guards checked by the server</h2><p>✓ Required documents attached to the instrument</p><p>✓ Bank-confirmed data remains separate from OCR</p><p>✓ No open critical or high discrepancy</p><p>✓ Separation of duties enforced for every decision</p><small>The next action depends on the case status and the signed-in role.</small></section><section className="panel release-steps"><h2>Steps</h2><div className="release-step-row"><span>REQUESTED</span><b>Case created</b><StatusBadge value={activeCase.status === "pending" ? "verified" : activeCase.status} /></div><div className="release-step-row"><span>{new Date(activeCase.created_at).toLocaleString("en-IN")}</span><b>{activeCase.reason}</b><span>Audit recorded</span></div></section></div><section className="panel release-action-panel"><h2>Next action</h2>{activeCase.status === "pending" && ["admin", "reviewer"].includes(role) ? <><p>Review the request independently from the person who prepared it.</p><textarea value={decisionNotes} onChange={(e) => setDecisionNotes(e.target.value)} placeholder="Decision notes (minimum 5 characters)" /><div className="form-actions"><button className="button ghost" disabled={decisionNotes.length < 5} onClick={() => decide(false)}>Reject case</button><button className="button primary" disabled={decisionNotes.length < 5} onClick={() => decide(true)}>Approve for execution</button></div></> : activeCase.status === "approved" && ["admin", "officer"].includes(role) ? <><p>Record the physical release with independent evidence.</p><input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="Execution evidence reference" /><button className="button primary" disabled={evidence.length < 3} onClick={execute}>Record execution</button></> : activeCase.status === "executed" && ["admin", "reviewer"].includes(role) ? <><p>Confirm closure after checking the execution evidence.</p><input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="Closure evidence reference" /><button className="button primary" disabled={evidence.length < 3} onClick={close}>Close case</button></> : <p className="muted">Nothing for your role to do at this stage.</p>}</section></>}{!activeCase && <section id="new-release-case" className="panel form-panel"><div className="form-panel-title"><div><h2>Start a new release case</h2><p>All decisions are persisted in the audit trail.</p></div><span className="step-pill">01 / REQUEST</span></div><div className="form-grid"><label>Instrument<select value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">Choose a verified FDR…</option>{fdrs.map((row) => <option value={row.id} key={row.id}>{row.identifier} · {row.status}</option>)}</select></label><label>Request type<select value={type} onChange={(e) => setType(e.target.value)}><option value="release">Release</option><option value="refund">Refund</option></select></label><label className="full">Reason<textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Provide the policy-backed reason and relevant context…" /></label></div><div className="form-actions"><span className="muted">Approval must be completed by a different authorised user.</span><button className="button primary" disabled={!selected || reason.length < 10} onClick={submit}>Submit request <Icon name="arrow" size={16} /></button></div>{message && <div className="success-message"><Icon name="check" size={15} />{message}</div>}</section>}{message && activeCase && <div className="success-message"><Icon name="check" size={15} />{message}</div>}</>;
}

function Policies({ setError, role }: { setError: (s: string) => void; role: string }) {
  const [rows, setRows] = useState<Policy[]>([]); const [show, setShow] = useState(false); const load = () => request<Policy[]>("/api/policies").then(setRows).catch((e) => setError(e.message)); useEffect(() => { load(); }, []);
  const toggle = async (row: Policy) => { try { await request(`/api/policies/${row.id}/status`, { method: "PATCH", body: JSON.stringify({ active: !row.active }) }); load(); } catch (e) { setError((e as Error).message); } };
  return <><PageHeader eyebrow="ADMINISTRATION / GOVERNANCE" title="Policy configuration" description="AICTE Approval Process Handbook security-deposit rules, preserved as versioned assessment inputs." action={role === "admin" ? <button className="button primary" onClick={() => setShow(true)}><Icon name="plus" size={16} />Add policy rule</button> : undefined} /><div className="info-banner"><Icon name="settings" size={18} /><div><b>Source-backed configuration</b><span>Loaded from AICTE Approval Process Handbook 2024-2027, Clause 1.12, Table 1.4. Amounts are shown in INR; private leased building / land rules require double the table amount.</span></div></div><section className="panel table-panel"><TableHeader title="Configured rules" subtitle={`${rows.length} policy versions · handbook values in force for the 2024-2027 period`} /><table><thead><tr><th>Rule</th><th>Description</th><th>Amount floor</th><th>Effective period</th><th>Status</th>{role === "admin" && <th />}</tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={row.id}><td><code>{row.rule_id}</code><small>{row.source_reference?.split(",")[0]}</small></td><td>{row.description}</td><td>{formatAmount(row.amount_floor)}</td><td>{new Date(row.effective_date).toLocaleDateString("en-IN")} – {row.expiry_date ? new Date(row.expiry_date).toLocaleDateString("en-IN") : "ongoing"}</td><td><StatusBadge value={row.active ? "verified" : "draft"} /></td>{role === "admin" && <td className="align-right"><button className="row-action" onClick={() => toggle(row)}>{row.active ? "Deactivate" : "Activate"}</button></td>}</tr>) : <tr><td colSpan={role === "admin" ? 6 : 5}><EmptyState text="No policy rules configured yet." /></td></tr>}</tbody></table></section>{show && <PolicyForm onClose={() => setShow(false)} onSaved={() => { setShow(false); load(); }} setError={setError} />}</>;
}

function Maturity({ setError }: { setError: (s: string) => void }) {
  const [rows, setRows] = useState<{ id: number; identifier: string; institution_id: number; institution_name: string; maturity_date: string; status: string; days_remaining: number }[]>([]);
  const [month, setMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [institutionFilter, setInstitutionFilter] = useState("all");
  useEffect(() => { request<typeof rows>("/api/maturity?days=730").then(setRows).catch((e) => setError(e.message)); }, [setError]);

  const institutions = useMemo(() => [...new Map(rows.map((row) => [row.institution_id, row.institution_name])).entries()].sort((a, b) => a[1].localeCompare(b[1])), [rows]);
  const visibleRows = institutionFilter === "all" ? rows : rows.filter((row) => String(row.institution_id) === institutionFilter);
  const monthPrefix = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`;
  const monthRows = visibleRows.filter((row) => row.maturity_date.slice(0, 7) === monthPrefix);
  const monthLength = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const calendarDays: (Date | null)[] = [
    ...Array.from({ length: new Date(month.getFullYear(), month.getMonth(), 1).getDay() }, () => null),
    ...Array.from({ length: monthLength }, (_, day) => new Date(month.getFullYear(), month.getMonth(), day + 1)),
  ];
  const colors = ["#1769aa", "#159269", "#a95791", "#bd732c", "#6878c7", "#11878e", "#bd5355"];
  const institutionColors = new Map(institutions.map(([id], index) => [id, colors[index % colors.length]]));
  const dayKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const todayKey = dayKey(new Date());
  const moveMonth = (amount: number) => setMonth((current) => new Date(current.getFullYear(), current.getMonth() + amount, 1));

  return <>
    <PageHeader eyebrow="LIFECYCLE / MONITORING" title="Maturity calendar" description="See every college’s FDR maturity dates together and coordinate governed follow-up." />
    <div className="info-banner"><Icon name="clock" size={18} /><div><b>Reminder policy applies</b><span>Dates follow the recorded maturity date. Calendar reminders do not grant release permission; verification and approval are still required.</span></div></div>
    <section className="maturity-summary" aria-label="Selected month summary">
      <div><span>Maturities this month</span><strong>{monthRows.length}</strong></div>
      <div><span>Colleges with maturities</span><strong>{new Set(monthRows.map((row) => row.institution_id)).size}</strong></div>
      <div><span>Overdue this month</span><strong>{monthRows.filter((row) => row.days_remaining < 0).length}</strong></div>
    </section>
    <section className="panel maturity-calendar-panel">
      <div className="maturity-calendar-toolbar">
        <div className="maturity-month-nav">
          <button className="button ghost" onClick={() => moveMonth(-1)} aria-label="Previous month">Previous</button>
          <h2>{month.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</h2>
          <button className="button ghost" onClick={() => moveMonth(1)} aria-label="Next month">Next</button>
          <button className="text-button" onClick={() => setMonth(new Date(new Date().getFullYear(), new Date().getMonth(), 1))}>Today</button>
        </div>
        <label className="maturity-college-filter">College
          <select value={institutionFilter} onChange={(event) => setInstitutionFilter(event.target.value)}>
            <option value="all">All colleges ({institutions.length})</option>
            {institutions.map(([id, name]) => <option value={id} key={id}>{name}</option>)}
          </select>
        </label>
      </div>
      <div className="maturity-calendar-scroll">
        <div className="maturity-calendar-grid" aria-label={`${month.toLocaleDateString("en-IN", { month: "long", year: "numeric" })} maturity dates`}>
          {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <div className="maturity-weekday" key={day}>{day}</div>)}
          {calendarDays.map((date, index) => {
            if (!date) return <div className="maturity-day maturity-day-empty" aria-hidden="true" key={`empty-${index}`} />;
            const dateKey = dayKey(date);
            const dayRows = monthRows.filter((row) => row.maturity_date.slice(0, 10) === dateKey);
            return <div className={`maturity-day${dateKey === todayKey ? " is-today" : ""}`} aria-label={`${date.toLocaleDateString("en-IN")}, ${dayRows.length} maturities`} key={dateKey}>
              <span className="maturity-day-number">{date.getDate()}{dateKey === todayKey && <i>Today</i>}</span>
              <div className="maturity-day-events">
                {dayRows.map((row) => <article className={`maturity-event${row.days_remaining < 0 ? " is-overdue" : row.days_remaining < 30 ? " is-soon" : ""}`} style={{ "--college-accent": institutionColors.get(row.institution_id) || colors[0] } as CSSProperties} key={row.id}>
                  <b title={row.institution_name}>{row.institution_name}</b>
                  <span title={row.identifier}>{row.identifier}</span>
                  <small>{row.days_remaining < 0 ? `${Math.abs(row.days_remaining)}d overdue` : row.days_remaining === 0 ? "Matures today" : `${row.days_remaining}d remaining`}</small>
                </article>)}
              </div>
            </div>;
          })}
        </div>
      </div>
      {!monthRows.length && <div className="maturity-empty"><EmptyState text={institutionFilter === "all" ? "No maturities for this month. Use the month controls to review other dates." : "This college has no maturities in the selected month."} /></div>}
      <div className="maturity-calendar-footnote">Upcoming and overdue records are shown according to your access. Select a college to focus the calendar.</div>
    </section>
    <section className="panel table-panel maturity-schedule">
      <TableHeader title="Maturity schedule" subtitle={`${visibleRows.length} instruments · filtered by the selected college`} />
      <table>
        <thead><tr><th>Instrument</th><th>College</th><th>Maturity date</th><th>Time remaining</th><th>Current status</th></tr></thead>
        <tbody>{visibleRows.length ? visibleRows.map((row) => <tr key={row.id}>
            <td><b>{row.identifier}</b></td>
            <td>{row.institution_name}</td>
            <td>{new Date(row.maturity_date).toLocaleDateString("en-IN")}</td>
            <td><span className={row.days_remaining < 0 ? "status status-rejected" : row.days_remaining < 30 ? "status status-release_requested" : "status status-draft"}>{row.days_remaining < 0 ? `${Math.abs(row.days_remaining)} days overdue` : row.days_remaining === 0 ? "Matures today" : `${row.days_remaining} days`}</span></td>
            <td><StatusBadge value={row.status} /></td>
          </tr>) : <tr><td colSpan={5}><EmptyState text="No maturity records match the selected college." /></td></tr>}</tbody>
      </table>
    </section>
  </>;
}

function Custody({ setError }: { setError: (s: string) => void }) {
  const [fdrs, setFdrs] = useState<Fdr[]>([]); const [selected, setSelected] = useState(""); const [events, setEvents] = useState<{ id: number; event_type: string; location: string; custodian: string; created_at: string }[]>([]); const [form, setForm] = useState({ event_type: "received", location: "", custodian: "", evidence_reference: "", remarks: "" });
  const load = (id: string) => { setSelected(id); if (id) request<typeof events>(`/api/fdrs/${id}/custody`).then(setEvents).catch((e) => setError(e.message)); };
  useEffect(() => { request<Fdr[]>("/api/fdrs").then(setFdrs).catch((e) => setError(e.message)); }, [setError]);
  const save = async () => { try { await request(`/api/fdrs/${selected}/custody`, { method: "POST", body: JSON.stringify(form) }); load(selected); } catch (e) { setError((e as Error).message); } };
  return <><PageHeader eyebrow="LIFECYCLE / PHYSICAL CONTROL" title="Custody register" description="Append-only custody events distinguish physical control from digital document integrity." /><div className="toolbar"><div className="field-search"><Icon name="search" size={16} /><select value={selected} onChange={(e) => load(e.target.value)}><option value="">Select an instrument…</option>{fdrs.map((row) => <option value={row.id} key={row.id}>{row.identifier} · {row.holder_name}</option>)}</select></div></div><section className="panel form-panel"><div className="form-grid"><label>Event type<select value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })}><option value="received">Received</option><option value="transferred">Transferred</option><option value="released">Released</option><option value="returned">Returned</option></select></label><label>Location<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Secure records room" /></label><label>Custodian<input value={form.custodian} onChange={(e) => setForm({ ...form, custodian: e.target.value })} /></label><label>Evidence reference<input value={form.evidence_reference} onChange={(e) => setForm({ ...form, evidence_reference: e.target.value })} /></label><label className="full">Remarks<textarea value={form.remarks} onChange={(e) => setForm({ ...form, remarks: e.target.value })} /></label></div><div className="form-actions"><button className="button primary" disabled={!selected || !form.location || !form.custodian} onClick={save}>Record custody event <Icon name="check" size={16} /></button></div></section><section className="panel table-panel"><TableHeader title="Custody timeline" subtitle={selected ? `${events.length} append-only events` : "Select an instrument above"} /><table><thead><tr><th>Event</th><th>Location</th><th>Custodian</th><th>Recorded</th></tr></thead><tbody>{events.map((event) => <tr key={event.id}><td><StatusBadge value={event.event_type} /></td><td>{event.location}</td><td>{event.custodian}</td><td>{new Date(event.created_at).toLocaleString("en-IN")}</td></tr>)}</tbody></table></section></>;
}

function Reports({ setError }: { setError: (s: string) => void }) {
  const download = async () => { try { const token = localStorage.getItem("vaulttrace_token"); const response = await fetch(`${API}/api/reports/instruments.csv`, { headers: { Authorization: `Bearer ${token}` } }); if (!response.ok) throw new Error("Export could not be generated"); const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = "vaulttrace-instruments.csv"; link.click(); URL.revokeObjectURL(url); } catch (e) { setError((e as Error).message); } };
  return <><PageHeader eyebrow="INSIGHTS / REPORTING" title="Reports & exports" description="Authorised, traceable extracts from the live registry." /><section className="dashboard-grid"><div className="panel action-panel"><div className="panel-heading"><div><h2>Instrument register</h2><p>CSV export of current FDR records</p></div></div><button onClick={download}><span className="quick-icon blue"><Icon name="download" /></span><span><b>Download CSV</b><small>Permission-checked export</small></span><Icon name="arrow" size={16} /></button></div><div className="panel guidance-card"><div className="eyebrow">EXPORT CONTROL</div><h2>Every export is intentional</h2><p>Reports are generated from the same access-controlled records shown in the workspace. Add audit logging for exports before production deployment.</p></div></section></>;
}

function Audit({ setError }: { setError: (s: string) => void }) {
  const [rows, setRows] = useState<{ id: number; actor_id: number; action: string; entity: string; entity_id: string; details: string; created_at: string }[]>([]);
  useEffect(() => { request<typeof rows>("/api/audit").then(setRows).catch((e) => setError(e.message)); }, [setError]);
  return <><PageHeader eyebrow="INSIGHTS / GOVERNANCE" title="Audit explorer" description="Review who changed what, when and against which entity." /><section className="panel table-panel"><TableHeader title="Activity trail" subtitle={`${rows.length} recent events`} /><table><thead><tr><th>Actor</th><th>Action</th><th>Entity</th><th>Details</th><th>Timestamp</th></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={row.id}><td>#{row.actor_id}</td><td><b>{row.action.replace(/_/g, " ")}</b></td><td><code>{row.entity}:{row.entity_id}</code></td><td>{row.details || "—"}</td><td>{new Date(row.created_at).toLocaleString("en-IN")}</td></tr>) : <tr><td colSpan={5}><EmptyState text="No audit events are available." /></td></tr>}</tbody></table></section></>;
}

function InstitutionForm({ onClose, onSaved, setError }: { onClose: () => void; onSaved: () => void; setError: (s: string) => void }) {
  const [name, setName] = useState(""); const [code, setCode] = useState(""); const [address, setAddress] = useState("");
  const save = async () => { try { await request("/api/institutions", { method: "POST", body: JSON.stringify({ name, code, address }) }); onSaved(); } catch (e) { setError((e as Error).message); } };
  return <Modal title="Add institution" onClose={onClose}><div className="form-grid"><label className="full">Institution name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. National Institute of Technology" /></label><label>Identifier<input value={code} onChange={(e) => setCode(e.target.value)} placeholder="INST-001" /></label><label>Address<input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="City, state" /></label></div><div className="form-actions"><button className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" disabled={name.length < 2 || code.length < 2} onClick={save}>Save institution</button></div></Modal>;
}

function FdrForm({ institutions, initialValues = {}, sourceDocumentId, onClose, onSaved, setError }: { institutions: Institution[]; initialValues?: FdrDraftValues; sourceDocumentId?: number; onClose: () => void; onSaved: (result?: { intake_id: number; status: string }) => void; setError: (s: string) => void }) {
  const [form, setForm] = useState({ identifier: initialValues.identifier || "", institution_id: initialValues.institution_id || "", approval_case_reference: initialValues.approval_case_reference || "", bank_name: initialValues.bank_name || "", branch_name: initialValues.branch_name || "", ifsc_code: initialValues.ifsc_code || "", amount: initialValues.amount || "", amount_in_words: initialValues.amount_in_words || "", issue_date: initialValues.issue_date || "", maturity_date: initialValues.maturity_date || "", beneficiary: initialValues.beneficiary || "", joint_holder: initialValues.joint_holder || "", lien_endorsed: true, lien_clause: "Irrevocable lien marked in favour of the designated beneficiary in the Core Banking System." });
  const [saveError, setSaveError] = useState("");
  const [saving, setSaving] = useState(false);
  const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const missing = [["FDR number", form.identifier], ["institution", form.institution_id], ["approval reference", form.approval_case_reference], ["bank", form.bank_name], ["branch", form.branch_name], ["IFSC", form.ifsc_code], ["amount", form.amount], ["amount in words", form.amount_in_words], ["issue date", form.issue_date], ["maturity date", form.maturity_date], ["beneficiary", form.beneficiary], ["joint holder", form.joint_holder]].filter(([, value]) => !value).map(([label]) => label);
  const issues = [...missing];
  if (form.ifsc_code && !validIfsc(form.ifsc_code)) issues.push("valid 11-character IFSC");
  if (form.amount && Number(form.amount) <= 0) issues.push("amount greater than zero");
  if (form.issue_date && form.maturity_date && form.maturity_date <= form.issue_date) issues.push("maturity date after issue date");
  if (form.lien_endorsed && form.lien_clause.trim().length < 5) issues.push("lien clause");
  const save = async () => {
    if (!sourceDocumentId && issues.length) {
      setSaveError(`Complete or correct these fields before submission: ${issues.join(", ")}.`);
      return;
    }
    setSaveError("");
    setSaving(true);
    try {
      if (sourceDocumentId) {
        const result = await request<{ id: number; status: string }>("/api/fdr-intakes", {
          method: "POST",
          body: JSON.stringify({ source_document_id: sourceDocumentId, fields: form }),
        });
        onSaved({ intake_id: result.id, status: result.status });
        return;
      }
      await request("/api/fdrs", { method: "POST", body: JSON.stringify({ ...form, holder_name: form.joint_holder || form.beneficiary, institution_id: Number(form.institution_id), amount: Number(form.amount), issue_date: new Date(form.issue_date).toISOString(), maturity_date: new Date(form.maturity_date).toISOString() }) });
      onSaved();
    } catch (e) {
      const message = (e as Error).message;
      setSaveError(message);
      setError(message);
    } finally {
      setSaving(false);
    }
  };
  return <Modal title="Register new security deposit / FDR instrument" onClose={onClose}><p className="modal-intro">{sourceDocumentId ? "Submit the extracted document as an incomplete draft. Missing values are left blank for review and are not invented." : "Declare the instrument exactly as shown on the supporting evidence. Submission creates a draft for scrutiny; it does not confirm authenticity."}</p>{saveError && <div className="form-error"><Icon name="alert" size={15} />{saveError}</div>}{!sourceDocumentId && issues.length > 0 && <div className="form-error"><Icon name="alert" size={15} />Required before submission: {issues.join(", ")}. Enter them from the original FDR.</div>}<div className="fdr-form-grid"><label>Target institution<select value={form.institution_id} onChange={(e) => update("institution_id", e.target.value)}><option value="">{initialValues.institution_name ? `Select institution (document: ${initialValues.institution_name})…` : "Select institution…"}</option>{initialValues.institution_id && !institutions.some((item) => String(item.id) === initialValues.institution_id) && <option value={initialValues.institution_id}>{initialValues.institution_name || "Document-matched institution"}</option>}{institutions.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select>{initialValues.institution_name && <small className="field-note">Institution extracted from document: {initialValues.institution_name}</small>}</label><label>Approval case reference<input value={form.approval_case_reference} onChange={(e) => update("approval_case_reference", e.target.value)} placeholder="APP-CASE-2026-001" /></label><label>FDR / certificate number<input value={form.identifier} onChange={(e) => update("identifier", e.target.value)} placeholder="FDR-SBI-609598019" /></label><label>Issuing scheduled bank<input value={form.bank_name} onChange={(e) => update("bank_name", e.target.value)} placeholder="State Bank of India" /></label><label>Branch name & IFSC<div className="split-fields"><input value={form.branch_name} onChange={(e) => update("branch_name", e.target.value)} placeholder="Main branch" /><input value={form.ifsc_code} onChange={(e) => update("ifsc_code", e.target.value.toUpperCase())} placeholder="SBIN0001234" /></div></label><label>Deposit principal sum (INR)<input type="number" min="1" value={form.amount} onChange={(e) => update("amount", e.target.value)} placeholder="Configured amount" /></label><label className="full">Amount in words<input value={form.amount_in_words} onChange={(e) => update("amount_in_words", e.target.value)} placeholder="Rupees … Only" /></label><label>Issue date<input type="date" value={form.issue_date} onChange={(e) => update("issue_date", e.target.value)} /></label><label>Maturity date (tenure)<input type="date" value={form.maturity_date} onChange={(e) => update("maturity_date", e.target.value)} /></label><label>Beneficiary (in favour of)<input value={form.beneficiary} onChange={(e) => update("beneficiary", e.target.value)} placeholder="Authorised beneficiary" /></label><label>Joint holder (institution)<input value={form.joint_holder} onChange={(e) => update("joint_holder", e.target.value)} placeholder="Principal & authorised signatory" /></label><div className="full lien-field"><span>Lien endorsement clause</span><label className="checkbox-label"><input type="checkbox" checked={form.lien_endorsed} onChange={(e) => setForm({ ...form, lien_endorsed: e.target.checked })} />Irrevocable lien recorded in the bank core banking system in favour of the beneficiary</label>{form.lien_endorsed && <input value={form.lien_clause} onChange={(e) => update("lien_clause", e.target.value)} />}</div></div><div className="form-actions"><button className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" disabled={saving} onClick={save}>{saving ? "Submitting…" : sourceDocumentId ? "Submit extracted draft" : "Submit FDR for scrutiny"} <Icon name={saving ? "clock" : "arrow"} size={16} /></button></div></Modal>;
}

function PolicyForm({ onClose, onSaved, setError }: { onClose: () => void; onSaved: () => void; setError: (s: string) => void }) {
  const [form, setForm] = useState({ rule_id: "", description: "", amount_floor: "", effective_date: "", source_reference: "" }); const update = (key: string, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const save = async () => { try { await request("/api/policies", { method: "POST", body: JSON.stringify({ ...form, amount_floor: Number(form.amount_floor), effective_date: new Date(form.effective_date).toISOString(), active: false, required_documents: [] }) }); onSaved(); } catch (e) { setError((e as Error).message); } };
  return <Modal title="Configure policy rule" onClose={onClose}><p className="modal-intro">Rules are inactive until authorised. Include a traceable source reference.</p><div className="form-grid"><label>Rule identifier<input value={form.rule_id} onChange={(e) => update("rule_id", e.target.value)} placeholder="POLICY-2026-01" /></label><label>Amount floor<input type="number" min="0" value={form.amount_floor} onChange={(e) => update("amount_floor", e.target.value)} /></label><label className="full">Description<input value={form.description} onChange={(e) => update("description", e.target.value)} /></label><label>Effective date<input type="date" value={form.effective_date} onChange={(e) => update("effective_date", e.target.value)} /></label><label>Source reference<input value={form.source_reference} onChange={(e) => update("source_reference", e.target.value)} placeholder="Circular / policy URL" /></label></div><div className="form-actions"><button className="button ghost" onClick={onClose}>Cancel</button><button className="button primary" disabled={!form.rule_id || !form.description || !form.effective_date} onClick={save}>Save inactive rule</button></div></Modal>;
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) { return <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal"><div className="modal-heading"><div><div className="eyebrow">VAULTTRACE WORKSPACE</div><h2>{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><Icon name="close" /></button></div>{children}</div></div>; }
function TableHeader({ title, subtitle }: { title: string; subtitle: string }) { return <div className="panel-heading"><div><h2>{title}</h2><p>{subtitle}</p></div><button className="icon-button"><Icon name="settings" size={17} /></button></div>; }
function FdrTable({ rows, institutions = [], emptyText = "No FDR records have been registered yet." }: { rows: Fdr[]; institutions?: Institution[]; emptyText?: string }) { const institutionName = (id: number) => institutions.find((item) => item.id === id)?.name || `Institution #${id}`; return <table><thead><tr><th>FDR record</th><th>Institution</th><th>Amount</th><th>Maturity</th><th>Status</th><th /></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={row.id}><td><b>{row.identifier}</b><small className="table-sub">{row.holder_name}</small></td><td>{institutionName(row.institution_id)}</td><td>{formatAmount(row.amount)}</td><td>{new Date(row.maturity_date).toLocaleDateString("en-IN")}</td><td><StatusBadge value={row.status} /></td><td className="align-right"><button className="row-action">Open <Icon name="arrow" size={14} /></button></td></tr>) : <tr><td colSpan={6}><EmptyState text={emptyText} /></td></tr>}</tbody></table>; }
function EmptyState({ text }: { text: string }) { return <div className="empty-state"><div className="empty-icon"><Icon name="file" size={20} /></div><span>{text}</span></div>; }
function LoadingRows({ cols }: { cols: number }) { return <>{[1, 2, 3].map((row) => <tr key={row}>{Array.from({ length: cols }).map((_, index) => <td key={index}><div className="skeleton" /></td>)}</tr>)}</>; }

createRoot(document.getElementById("root")!).render(<App />);
