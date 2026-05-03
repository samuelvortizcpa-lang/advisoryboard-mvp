import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import EmptyCadenceState from "@/components/cadence/EmptyCadenceState";

describe("EmptyCadenceState", () => {
  it("renders empty message", () => {
    render(<EmptyCadenceState isAdmin onPickClick={() => {}} />);
    expect(
      screen.getByText("No cadence assigned. Pick a template to get started.")
    ).toBeInTheDocument();
  });

  it("Pick button visible and enabled for admin", () => {
    render(<EmptyCadenceState isAdmin onPickClick={() => {}} />);
    const btn = screen.getByRole("button", { name: "Pick template" });
    expect(btn).toBeEnabled();
  });

  it("Pick button disabled for non-admin", () => {
    render(<EmptyCadenceState isAdmin={false} onPickClick={() => {}} />);
    const btn = screen.getByRole("button", { name: "Pick template" });
    expect(btn).toBeDisabled();
    expect(screen.getByText("Admin only")).toBeInTheDocument();
  });
});
