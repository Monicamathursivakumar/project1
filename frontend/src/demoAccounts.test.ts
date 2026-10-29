import { describe, expect, it } from "vitest";
import { demoAccounts } from "./demoAccounts";

describe("demo role previews", () => {
  it("shows a distinct role-specific workflow for each demo account", () => {
    const accountsByUsername = new Map(demoAccounts.map((account) => [account.username, account]));
    const expectedPreviews = [
      ["demo_institution_user", "Draft registration and verified FDRs"],
      ["demo_reviewing_officer", "Open discrepancies and review cases"],
      ["demo_verification_officer", "Pending and completed bank confirmation cases"],
      ["demo_custody_officer", "Release handovers and custody history"],
      ["demo_policy_administrator", "Policy rules and assessment examples"],
      ["demo_auditor", "Cross-institution audit and reports"],
      ["demo_administrator", "System-wide registry and account approvals"],
      ["demo_viewer", "Read-only closed and active instruments"],
    ] as const;

    expect(demoAccounts).toHaveLength(expectedPreviews.length);
    expect(accountsByUsername.size).toBe(demoAccounts.length);
    for (const [username, description] of expectedPreviews) {
      expect(accountsByUsername.get(username)?.description).toBe(description);
    }
  });
});
