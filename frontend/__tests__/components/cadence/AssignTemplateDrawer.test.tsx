import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import type { CadenceTemplateListResponse } from "@/lib/api";

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

const mockListTemplates = vi.fn<() => Promise<CadenceTemplateListResponse>>();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createCadenceApi: () => ({
      listTemplates: mockListTemplates,
    }),
  };
});

import AssignTemplateDrawer from "@/components/cadence/AssignTemplateDrawer";

const TEMPLATES: CadenceTemplateListResponse = {
  templates: [
    { id: "sys-1", name: "Full Cadence", description: "All 7 deliverables", is_system: true, is_active: true },
    { id: "sys-2", name: "Empty Cadence", description: null, is_system: true, is_active: true },
    { id: "cust-1", name: "Firm Custom", description: "Custom for firm", is_system: false, is_active: true },
  ],
};

beforeEach(() => {
  mockListTemplates.mockResolvedValue(TEMPLATES);
});

describe("AssignTemplateDrawer", () => {
  it("renders system and custom sections separately when open", async () => {
    render(
      <AssignTemplateDrawer
        open
        onClose={() => {}}
        currentTemplateId={null}
        onAssign={vi.fn()}
      />
    );
    await waitFor(() => {
      expect(screen.getByText("System templates")).toBeInTheDocument();
    });
    expect(screen.getByText("Your custom templates")).toBeInTheDocument();
    expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    expect(screen.getByText("Firm Custom")).toBeInTheDocument();
  });

  it("Confirm button disabled until a different template selected", async () => {
    render(
      <AssignTemplateDrawer
        open
        onClose={() => {}}
        currentTemplateId="sys-1"
        onAssign={vi.fn()}
      />
    );
    await waitFor(() => {
      expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    });
    // Confirm should be disabled initially (nothing selected)
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    // Select the current template — Confirm still disabled
    fireEvent.click(screen.getByText("Full Cadence"));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();

    // Select a different template — Confirm enabled
    fireEvent.click(screen.getByText("Firm Custom"));
    expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("selecting and confirming calls onAssign with selected templateId", async () => {
    const onAssign = vi.fn().mockResolvedValue(undefined);
    render(
      <AssignTemplateDrawer
        open
        onClose={() => {}}
        currentTemplateId={null}
        onAssign={onAssign}
      />
    );
    await waitFor(() => {
      expect(screen.getByText("Firm Custom")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Firm Custom"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(onAssign).toHaveBeenCalledWith("cust-1");
    });
  });
});
