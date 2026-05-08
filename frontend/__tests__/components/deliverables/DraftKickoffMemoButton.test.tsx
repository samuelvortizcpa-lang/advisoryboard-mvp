import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

const stableGetToken = vi.fn().mockResolvedValue("test-token");

// Mock Clerk
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

// Mock OrgContext — default: admin
const mockOrgReturn = { activeOrg: { id: "org-1", role: "admin", org_type: "firm" }, isAdmin: true };
vi.mock("@/contexts/OrgContext", () => ({
  useOrg: () => mockOrgReturn,
}));

// Mock cadence API
const mockGetEnabledDeliverables = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createCadenceApi: () => ({
      getEnabledDeliverables: mockGetEnabledDeliverables,
    }),
  };
});

// Mock the modal to a stub so we can check its props
vi.mock("@/components/deliverables/KickoffMemoDraftModal", () => ({
  default: (props: { open: boolean }) => (
    <div data-testid="kickoff-modal" data-open={props.open} />
  ),
}));

import DraftKickoffMemoButton from "@/components/deliverables/DraftKickoffMemoButton";

beforeEach(() => {
  mockGetEnabledDeliverables.mockReset();
  mockOrgReturn.activeOrg = { id: "org-1", role: "admin", org_type: "firm" };
  mockOrgReturn.isAdmin = true;
});

describe("DraftKickoffMemoButton", () => {
  it("does not render when user is not admin", async () => {
    mockOrgReturn.isAdmin = false;
    mockGetEnabledDeliverables.mockResolvedValue({ enabled: ["kickoff_memo"] });

    render(
      <DraftKickoffMemoButton clientId="c1" clientName="Test" clientEmail="t@t.com" />
    );

    // Wait for the effect to settle
    await waitFor(() => {
      expect(mockGetEnabledDeliverables).toHaveBeenCalled();
    });

    expect(screen.queryByRole("button", { name: /draft kickoff/i })).toBeNull();
  });

  it("does not render when kickoff_memo is not in enabledDeliverables", async () => {
    mockGetEnabledDeliverables.mockResolvedValue({ enabled: ["quarterly_memo"] });

    render(
      <DraftKickoffMemoButton clientId="c1" clientName="Test" clientEmail="t@t.com" />
    );

    await waitFor(() => {
      expect(mockGetEnabledDeliverables).toHaveBeenCalled();
    });

    expect(screen.queryByRole("button", { name: /draft kickoff/i })).toBeNull();
  });

  it("renders and opens modal on click when admin and enabled", async () => {
    mockGetEnabledDeliverables.mockResolvedValue({ enabled: ["kickoff_memo"] });

    render(
      <DraftKickoffMemoButton clientId="c1" clientName="Test" clientEmail="t@t.com" />
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /draft kickoff/i })).toBeInTheDocument();
    });

    // Modal starts closed
    expect(screen.getByTestId("kickoff-modal").dataset.open).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: /draft kickoff/i }));

    expect(screen.getByTestId("kickoff-modal").dataset.open).toBe("true");
  });
});
