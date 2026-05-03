import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import type { CadenceTemplateListResponse } from "@/lib/api";

const stableGetToken = vi.fn().mockResolvedValue("test-token");

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

const stableRefreshOrgs = vi.fn().mockResolvedValue(undefined);

let stableOrg: Record<string, unknown> = {
  id: "org-1",
  role: "admin",
  org_type: "firm",
  default_cadence_template_id: "sys-1",
};

vi.mock("@/contexts/OrgContext", () => ({
  useOrg: () => ({
    activeOrg: stableOrg,
    isAdmin: true,
    refreshOrgs: stableRefreshOrgs,
  }),
}));

const mockListTemplates = vi.fn<() => Promise<CadenceTemplateListResponse>>();
const mockSetFirmDefault = vi.fn<() => Promise<void>>();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createCadenceApi: () => ({
      listTemplates: mockListTemplates,
      setFirmDefault: mockSetFirmDefault,
    }),
  };
});

import FirmDefaultCard from "@/components/cadence/FirmDefaultCard";

const TEMPLATES: CadenceTemplateListResponse = {
  templates: [
    { id: "sys-1", name: "Full Cadence", description: "All 7", is_system: true, is_active: true },
    { id: "sys-2", name: "Empty", description: null, is_system: true, is_active: true },
    { id: "cust-1", name: "Custom One", description: null, is_system: false, is_active: true },
  ],
};

beforeEach(() => {
  mockListTemplates.mockReset().mockResolvedValue(TEMPLATES);
  mockSetFirmDefault.mockReset().mockResolvedValue(undefined);
  stableRefreshOrgs.mockReset().mockResolvedValue(undefined);
  stableOrg = {
    id: "org-1",
    role: "admin",
    org_type: "firm",
    default_cadence_template_id: "sys-1",
  };
});

describe("FirmDefaultCard", () => {
  it("renders 'Currently using: {name}' when firm default is set", async () => {
    render(<FirmDefaultCard isAdmin={true} />);
    await waitFor(() => {
      expect(screen.getByText("Currently using: Full Cadence")).toBeInTheDocument();
    });
  });

  it("renders 'No firm default set' when not set", async () => {
    stableOrg = { ...stableOrg, default_cadence_template_id: null };
    render(<FirmDefaultCard isAdmin={true} />);
    await waitFor(() => {
      expect(screen.getByText("No firm default set")).toBeInTheDocument();
    });
  });

  it("admin sees Change button; non-admin does not", async () => {
    const { unmount } = render(<FirmDefaultCard isAdmin={true} />);
    await waitFor(() => {
      expect(screen.getByText("Currently using: Full Cadence")).toBeInTheDocument();
    });
    expect(screen.getByText("Change")).toBeInTheDocument();
    unmount();

    render(<FirmDefaultCard isAdmin={false} />);
    await waitFor(() => {
      expect(screen.getByText("Currently using: Full Cadence")).toBeInTheDocument();
    });
    expect(screen.queryByText("Change")).not.toBeInTheDocument();
  });

  it("selecting + confirming new template calls setFirmDefault with correct args", async () => {
    render(<FirmDefaultCard isAdmin={true} />);
    await waitFor(() => {
      expect(screen.getByText("Change")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Change"));
    fireEvent.click(screen.getByText("Custom One"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(mockSetFirmDefault).toHaveBeenCalledWith("org-1", "cust-1");
    });
    expect(stableRefreshOrgs).toHaveBeenCalled();
  });

  it("clearing default calls setFirmDefault(orgId, null)", async () => {
    render(<FirmDefaultCard isAdmin={true} />);
    await waitFor(() => {
      expect(screen.getByText("Change")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Change"));
    fireEvent.click(screen.getByText("Clear default"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(mockSetFirmDefault).toHaveBeenCalledWith("org-1", null);
    });
  });
});
