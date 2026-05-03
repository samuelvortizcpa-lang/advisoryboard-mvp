import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import type { ClientCadenceResponse } from "@/lib/api";
import ActiveCadenceCard from "@/components/cadence/ActiveCadenceCard";

function makeCadence(
  overrides: Partial<ClientCadenceResponse> = {}
): ClientCadenceResponse {
  return {
    client_id: "c-1",
    template_id: "t-1",
    template_name: "Full Cadence",
    template_is_system: true,
    overrides: {},
    effective_flags: {
      kickoff_memo: true,
      progress_note: true,
      quarterly_memo: true,
      mid_year_tune_up: false,
      year_end_recap: true,
      pre_prep_brief: true,
      post_prep_flag: true,
    },
    ...overrides,
  };
}

describe("ActiveCadenceCard", () => {
  it("renders template name, system badge, and enabled-count summary", () => {
    render(
      <ActiveCadenceCard cadence={makeCadence()} isAdmin onChangeClick={() => {}} />
    );
    expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByText("6 of 7 deliverables enabled")).toBeInTheDocument();
  });

  it("shows Custom badge for non-system template", () => {
    render(
      <ActiveCadenceCard
        cadence={makeCadence({ template_is_system: false })}
        isAdmin
        onChangeClick={() => {}}
      />
    );
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("Change button visible and enabled for admin", () => {
    const onClick = vi.fn();
    render(
      <ActiveCadenceCard cadence={makeCadence()} isAdmin onChangeClick={onClick} />
    );
    const btn = screen.getByRole("button", { name: "Change" });
    expect(btn).toBeEnabled();
  });

  it("Change button disabled with 'Admin only' for non-admin", () => {
    render(
      <ActiveCadenceCard
        cadence={makeCadence()}
        isAdmin={false}
        onChangeClick={() => {}}
      />
    );
    const btn = screen.getByRole("button", { name: "Change" });
    expect(btn).toBeDisabled();
    expect(screen.getByText("Admin only")).toBeInTheDocument();
  });
});
