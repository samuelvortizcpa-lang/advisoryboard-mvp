import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

import type { ClientCadenceResponse } from "@/lib/api";

const stableGetToken = vi.fn().mockResolvedValue("test-token");

// Mock Clerk
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

// Mock OrgContext
const stableOrg = { id: "org-1", role: "admin", org_type: "firm" };
vi.mock("@/contexts/OrgContext", () => ({
  useOrg: () => ({
    activeOrg: stableOrg,
    isAdmin: true,
  }),
}));

const mockGetClientCadence = vi.fn<() => Promise<ClientCadenceResponse>>();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createCadenceApi: () => ({
      getClientCadence: mockGetClientCadence,
      assignCadence: vi.fn(),
      updateOverrides: vi.fn(),
      listTemplates: vi.fn().mockResolvedValue({ templates: [] }),
    }),
  };
});

import CadenceTab from "@/components/cadence/CadenceTab";

const CADENCE_RESPONSE: ClientCadenceResponse = {
  client_id: "c-1",
  template_id: "t-1",
  template_name: "Full Cadence",
  template_is_system: true,
  overrides: {},
  effective_flags: {
    kickoff_memo: true,
    progress_note: true,
    quarterly_memo: true,
    mid_year_tune_up: true,
    year_end_recap: true,
    pre_prep_brief: true,
    post_prep_flag: true,
  },
};

beforeEach(() => {
  mockGetClientCadence.mockReset();
});

describe("CadenceTab", () => {
  it("renders skeleton on mount before fetch resolves", () => {
    // Never resolve the promise — stays in loading state
    mockGetClientCadence.mockReturnValue(new Promise(() => {}));
    const { container } = render(<CadenceTab clientId="c-1" />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });

  it("renders grid + card when fetch returns assigned cadence", async () => {
    mockGetClientCadence.mockResolvedValue(CADENCE_RESPONSE);
    render(<CadenceTab clientId="c-1" />);
    await waitFor(() => {
      expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    });
    // Card shows enabled count
    expect(screen.getByText("7 of 7 deliverables enabled")).toBeInTheDocument();
    // Grid shows deliverable labels
    expect(screen.getByText("Kickoff memo")).toBeInTheDocument();
    expect(screen.getByText("Post-prep flag")).toBeInTheDocument();
  });

  it("renders EmptyCadenceState when fetch returns 404", async () => {
    mockGetClientCadence.mockRejectedValue({ status: 404, message: "Not found" });
    render(<CadenceTab clientId="c-1" />);
    await waitFor(() => {
      expect(
        screen.getByText("No cadence assigned. Pick a template to get started.")
      ).toBeInTheDocument();
    });
  });
});
