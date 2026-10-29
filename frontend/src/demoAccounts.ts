export type DemoAccount = {
  username: string;
  label: string;
  role: string;
  description: string;
};

export const demoAccounts: DemoAccount[] = [
  { username: "demo_institution_user", label: "Institution User", role: "Institution User", description: "Draft registration and verified FDRs" },
  { username: "demo_reviewing_officer", label: "Reviewing Officer", role: "Reviewing Officer", description: "Open discrepancies and review cases" },
  { username: "demo_verification_officer", label: "Verification Officer", role: "Verification Officer", description: "Pending and completed bank confirmation cases" },
  { username: "demo_custody_officer", label: "Custody Officer", role: "Custody Officer", description: "Release handovers and custody history" },
  { username: "demo_policy_administrator", label: "Policy Administrator", role: "Policy Administrator", description: "Policy rules and assessment examples" },
  { username: "demo_auditor", label: "Auditor", role: "Auditor", description: "Cross-institution audit and reports" },
  { username: "demo_administrator", label: "Administrator", role: "Administrator", description: "System-wide registry and account approvals" },
  { username: "demo_viewer", label: "Viewer", role: "Viewer", description: "Read-only closed and active instruments" },
];
