import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

import type { CadenceTemplateDetailResponse } from "@/lib/api";

const stableGetToken = vi.fn().mockResolvedValue("test-token");

vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

const stableOrg = { id: "org-1", role: "admin", org_type: "firm" };
vi.mock("@/contexts/OrgContext", () => ({
  useOrg: () => ({
    activeOrg: stableOrg,
    isAdmin: true,
  }),
}));

const mockCreateTemplate = vi.fn<() => Promise<CadenceTemplateDetailResponse>>();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createCadenceApi: () => ({
      createTemplate: mockCreateTemplate,
    }),
  };
});

import CreateTemplateDialog from "@/components/cadence/CreateTemplateDialog";

beforeEach(() => {
  mockCreateTemplate.mockReset();
});

describe("CreateTemplateDialog", () => {
  it("requires name — Create button disabled when name is empty", () => {
    render(
      <CreateTemplateDialog open onClose={() => {}} onCreated={() => {}} />,
    );
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("all 7 deliverable flags rendered with default false", () => {
    render(
      <CreateTemplateDialog open onClose={() => {}} onCreated={() => {}} />,
    );
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(7);
    for (const cb of checkboxes) {
      expect(cb).not.toBeChecked();
    }
  });

  it("submit calls createTemplate with full payload (all 7 keys present)", async () => {
    mockCreateTemplate.mockResolvedValue({
      id: "new-1",
      name: "Test",
      description: null,
      is_system: false,
      is_active: true,
      deliverable_flags: {
        kickoff_memo: false,
        progress_note: false,
        quarterly_memo: false,
        mid_year_tune_up: false,
        year_end_recap: false,
        pre_prep_brief: false,
        post_prep_flag: false,
      },
    });
    const onCreated = vi.fn();
    render(
      <CreateTemplateDialog open onClose={() => {}} onCreated={onCreated} />,
    );

    fireEvent.change(screen.getByPlaceholderText("e.g. Quarterly Focus"), {
      target: { value: "Test Template" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(mockCreateTemplate).toHaveBeenCalledWith({
        name: "Test Template",
        description: null,
        deliverable_flags: {
          kickoff_memo: false,
          progress_note: false,
          quarterly_memo: false,
          mid_year_tune_up: false,
          year_end_recap: false,
          pre_prep_brief: false,
          post_prep_flag: false,
        },
      });
    });
    expect(onCreated).toHaveBeenCalledWith("new-1");
  });

  it("backdrop click closes dialog", () => {
    const onClose = vi.fn();
    render(
      <CreateTemplateDialog open onClose={onClose} onCreated={() => {}} />,
    );
    // Click the backdrop (outermost div)
    const backdrop = screen.getByText("Create Custom Template").closest(".fixed");
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalled();
  });

  it("backend error renders inline", async () => {
    mockCreateTemplate.mockRejectedValue(new Error("Name already exists"));
    render(
      <CreateTemplateDialog open onClose={() => {}} onCreated={() => {}} />,
    );

    fireEvent.change(screen.getByPlaceholderText("e.g. Quarterly Focus"), {
      target: { value: "Duplicate" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(screen.getByText("Name already exists")).toBeInTheDocument();
    });
  });
});
