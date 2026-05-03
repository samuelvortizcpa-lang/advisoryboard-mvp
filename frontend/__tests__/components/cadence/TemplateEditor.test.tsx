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

const mockUpdateTemplate = vi.fn<() => Promise<CadenceTemplateDetailResponse>>();
const mockDeactivateTemplate = vi.fn<() => Promise<void>>();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createCadenceApi: () => ({
      updateTemplate: mockUpdateTemplate,
      deactivateTemplate: mockDeactivateTemplate,
    }),
  };
});

import TemplateEditor from "@/components/cadence/TemplateEditor";

const SYSTEM_TEMPLATE: CadenceTemplateDetailResponse = {
  id: "sys-1",
  name: "Full Cadence",
  description: "All deliverables",
  is_system: true,
  is_active: true,
  deliverable_flags: {
    kickoff_memo: true,
    progress_note: true,
    quarterly_memo: true,
    mid_year_tune_up: true,
    year_end_recap: true,
    pre_prep_brief: true,
    post_prep_flag: true,
  },
};

const CUSTOM_TEMPLATE: CadenceTemplateDetailResponse = {
  id: "cust-1",
  name: "Quarterly Focus",
  description: "Q only",
  is_system: false,
  is_active: true,
  deliverable_flags: {
    kickoff_memo: false,
    progress_note: false,
    quarterly_memo: true,
    mid_year_tune_up: false,
    year_end_recap: true,
    pre_prep_brief: false,
    post_prep_flag: false,
  },
};

beforeEach(() => {
  mockUpdateTemplate.mockReset();
  mockDeactivateTemplate.mockReset();
});

describe("TemplateEditor", () => {
  it("system template: read-only notice visible, no save or deactivate buttons", () => {
    render(
      <TemplateEditor
        template={SYSTEM_TEMPLATE}
        isAdmin={true}
        onSaved={vi.fn()}
        onDeactivated={vi.fn()}
      />,
    );
    expect(screen.getByText("System template (read-only)")).toBeInTheDocument();
    expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    expect(screen.queryByText("Save changes")).not.toBeInTheDocument();
    expect(screen.queryByText("Deactivate template")).not.toBeInTheDocument();
  });

  it("custom template: name/description/flags editable", () => {
    render(
      <TemplateEditor
        template={CUSTOM_TEMPLATE}
        isAdmin={true}
        onSaved={vi.fn()}
        onDeactivated={vi.fn()}
      />,
    );
    const nameInput = screen.getByDisplayValue("Quarterly Focus");
    expect(nameInput).not.toBeDisabled();
    const descInput = screen.getByDisplayValue("Q only");
    expect(descInput).not.toBeDisabled();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(7);
    for (const cb of checkboxes) {
      expect(cb).not.toBeDisabled();
    }
  });

  it("Save calls onSaved with updated payload from updateTemplate response", async () => {
    const updatedTemplate = { ...CUSTOM_TEMPLATE, name: "Updated Name" };
    mockUpdateTemplate.mockResolvedValue(updatedTemplate);
    const onSaved = vi.fn();
    render(
      <TemplateEditor
        template={CUSTOM_TEMPLATE}
        isAdmin={true}
        onSaved={onSaved}
        onDeactivated={vi.fn()}
      />,
    );

    const nameInput = screen.getByDisplayValue("Quarterly Focus");
    fireEvent.change(nameInput, { target: { value: "Updated Name" } });
    fireEvent.click(screen.getByText("Save changes"));

    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledWith(updatedTemplate);
    });
  });

  it("Deactivate calls onDeactivated on success", async () => {
    mockDeactivateTemplate.mockResolvedValue(undefined);
    const onDeactivated = vi.fn();
    render(
      <TemplateEditor
        template={CUSTOM_TEMPLATE}
        isAdmin={true}
        onSaved={vi.fn()}
        onDeactivated={onDeactivated}
      />,
    );

    fireEvent.click(screen.getByText("Deactivate template"));

    await waitFor(() => {
      expect(onDeactivated).toHaveBeenCalled();
    });
  });

  it("Deactivate failure renders backend error message inline", async () => {
    mockDeactivateTemplate.mockRejectedValue(
      new Error("This template is still in use. Reassign clients before deactivating."),
    );
    render(
      <TemplateEditor
        template={CUSTOM_TEMPLATE}
        isAdmin={true}
        onSaved={vi.fn()}
        onDeactivated={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("Deactivate template"));

    await waitFor(() => {
      expect(
        screen.getByText(
          "This template is still in use. Reassign clients before deactivating.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("non-admin: read-only even on custom template (no save/deactivate)", () => {
    render(
      <TemplateEditor
        template={CUSTOM_TEMPLATE}
        isAdmin={false}
        onSaved={vi.fn()}
        onDeactivated={vi.fn()}
      />,
    );
    const nameInput = screen.getByDisplayValue("Quarterly Focus");
    expect(nameInput).toBeDisabled();
    const checkboxes = screen.getAllByRole("checkbox");
    for (const cb of checkboxes) {
      expect(cb).toBeDisabled();
    }
    expect(screen.queryByText("Save changes")).not.toBeInTheDocument();
    expect(screen.queryByText("Deactivate template")).not.toBeInTheDocument();
  });
});
