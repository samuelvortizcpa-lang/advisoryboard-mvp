/**
 * Tests for OrgContext — multi-tenant organization switching.
 *
 * Verifies that:
 * - Firm org is preferred over personal workspace
 * - isAdmin and isPersonalOrg are derived correctly
 * - Org list fetching works
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { OrgProvider, useOrg } from "@/contexts/OrgContext";

// Mock Clerk
const mockGetToken = vi.fn().mockResolvedValue("mock-token");
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    getToken: mockGetToken,
    isLoaded: true,
    isSignedIn: true,
  }),
}));

// Mock API
const mockListOrgs = vi.fn();
vi.mock("@/lib/api", () => ({
  createOrganizationsApi: () => ({
    list: mockListOrgs,
  }),
}));

// Test consumer component
function OrgConsumer() {
  const { orgs, activeOrg, isAdmin, isPersonalOrg, isLoading } = useOrg();
  return (
    <div>
      <span data-testid="loading">{String(isLoading)}</span>
      <span data-testid="org-count">{orgs.length}</span>
      <span data-testid="active-org">{activeOrg?.name ?? "none"}</span>
      <span data-testid="is-admin">{String(isAdmin)}</span>
      <span data-testid="is-personal">{String(isPersonalOrg)}</span>
    </div>
  );
}

describe("OrgContext", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("prefers firm org over personal", async () => {
    mockListOrgs.mockResolvedValue([
      { id: "org-1", name: "Personal", org_type: "personal", role: "admin" },
      { id: "org-2", name: "My Firm", org_type: "firm", role: "admin" },
    ]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("active-org").textContent).toBe("My Firm");
    });
  });

  it("falls back to first org when no firm exists", async () => {
    mockListOrgs.mockResolvedValue([
      { id: "org-1", name: "Personal", org_type: "personal", role: "admin" },
    ]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("active-org").textContent).toBe("Personal");
    });
  });

  it("derives isAdmin from org role", async () => {
    mockListOrgs.mockResolvedValue([
      { id: "org-1", name: "Team", org_type: "firm", role: "admin" },
    ]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("is-admin").textContent).toBe("true");
    });
  });

  it("derives isAdmin=false for member role", async () => {
    mockListOrgs.mockResolvedValue([
      { id: "org-1", name: "Team", org_type: "firm", role: "member" },
    ]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("is-admin").textContent).toBe("false");
    });
  });

  it("derives isPersonalOrg from org_type", async () => {
    mockListOrgs.mockResolvedValue([
      { id: "org-1", name: "Personal", org_type: "personal", role: "admin" },
    ]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("is-personal").textContent).toBe("true");
    });
  });

  it("isPersonalOrg=false for firm org", async () => {
    mockListOrgs.mockResolvedValue([
      { id: "org-1", name: "Firm", org_type: "firm", role: "admin" },
    ]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("is-personal").textContent).toBe("false");
    });
  });

  it("handles empty org list gracefully", async () => {
    mockListOrgs.mockResolvedValue([]);

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });
    expect(screen.getByTestId("active-org").textContent).toBe("none");
    expect(screen.getByTestId("org-count").textContent).toBe("0");
  });

  it("handles API error gracefully", async () => {
    mockListOrgs.mockRejectedValue(new Error("Network error"));

    render(
      <OrgProvider>
        <OrgConsumer />
      </OrgProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId("loading").textContent).toBe("false");
    });
    expect(screen.getByTestId("active-org").textContent).toBe("none");
  });
});
