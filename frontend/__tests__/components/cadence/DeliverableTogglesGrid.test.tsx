import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import type { DeliverableKey } from "@/lib/api";
import { DELIVERABLE_KEYS, DELIVERABLE_LABELS } from "@/lib/api";
import DeliverableTogglesGrid from "@/components/cadence/DeliverableTogglesGrid";

const ALL_TRUE: Record<DeliverableKey, boolean> = {
  kickoff_memo: true,
  progress_note: true,
  quarterly_memo: true,
  mid_year_tune_up: true,
  year_end_recap: true,
  pre_prep_brief: true,
  post_prep_flag: true,
};

function renderGrid(props: Partial<React.ComponentProps<typeof DeliverableTogglesGrid>> = {}) {
  const defaults = {
    effectiveFlags: ALL_TRUE,
    overrides: {} as Partial<Record<DeliverableKey, boolean>>,
    isAdmin: true,
    onToggle: vi.fn(),
    onResetAll: vi.fn(),
  };
  return render(<DeliverableTogglesGrid {...defaults} {...props} />);
}

describe("DeliverableTogglesGrid", () => {
  it("renders 7 rows in DELIVERABLE_KEYS order with correct labels", () => {
    renderGrid();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(7);
    for (const key of DELIVERABLE_KEYS) {
      expect(screen.getByText(DELIVERABLE_LABELS[key])).toBeInTheDocument();
    }
  });

  it("toggle clicked by admin calls onToggle with correct args", () => {
    const onToggle = vi.fn();
    renderGrid({ onToggle });
    const checkboxes = screen.getAllByRole("checkbox");
    // Click first checkbox (kickoff_memo, currently true → should call with false)
    fireEvent.click(checkboxes[0]);
    expect(onToggle).toHaveBeenCalledWith("kickoff_memo", false);
  });

  it("toggles disabled for non-admin", () => {
    renderGrid({ isAdmin: false });
    const checkboxes = screen.getAllByRole("checkbox");
    for (const cb of checkboxes) {
      expect(cb).toBeDisabled();
    }
  });

  it("override-count subtitle shows 0 overrides", () => {
    renderGrid({ overrides: {} });
    expect(
      screen.getByText("All deliverables follow template defaults")
    ).toBeInTheDocument();
  });

  it("override-count subtitle shows 1 override", () => {
    renderGrid({ overrides: { kickoff_memo: false } });
    expect(screen.getByText("1 of 7 currently overridden")).toBeInTheDocument();
  });

  it("override-count subtitle shows 2 overrides", () => {
    renderGrid({
      overrides: { kickoff_memo: false, progress_note: false },
    });
    expect(screen.getByText("2 of 7 currently overridden")).toBeInTheDocument();
  });

  it("Reset all hidden when no overrides", () => {
    renderGrid({ overrides: {} });
    expect(screen.queryByText("Reset all")).not.toBeInTheDocument();
  });

  it("Reset all visible and enabled when overrides exist (admin)", () => {
    renderGrid({ overrides: { kickoff_memo: false }, isAdmin: true });
    const btn = screen.getByText("Reset all");
    expect(btn).toBeEnabled();
  });

  it("Reset all disabled for non-admin when overrides exist", () => {
    renderGrid({ overrides: { kickoff_memo: false }, isAdmin: false });
    const btn = screen.getByText("Reset all");
    expect(btn).toBeDisabled();
  });
});
