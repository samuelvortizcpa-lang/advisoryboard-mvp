import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import type { CadenceTemplateSummary } from "@/lib/api";
import TemplateRow from "@/components/cadence/TemplateRow";

const SYSTEM_TEMPLATE: CadenceTemplateSummary = {
  id: "sys-1",
  name: "Full Cadence",
  description: "All 7 deliverables",
  is_system: true,
  is_active: true,
};

const CUSTOM_TEMPLATE: CadenceTemplateSummary = {
  id: "cust-1",
  name: "Quarterly Focus",
  description: null,
  is_system: false,
  is_active: true,
};

const INACTIVE_TEMPLATE: CadenceTemplateSummary = {
  id: "cust-2",
  name: "Old Template",
  description: "Deprecated",
  is_system: false,
  is_active: false,
};

describe("TemplateRow", () => {
  it("renders name + System badge for system template", () => {
    render(<TemplateRow template={SYSTEM_TEMPLATE} href="/templates/sys-1" />);
    expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByText("All 7 deliverables")).toBeInTheDocument();
  });

  it("renders Custom badge for custom template", () => {
    render(<TemplateRow template={CUSTOM_TEMPLATE} href="/templates/cust-1" />);
    expect(screen.getByText("Quarterly Focus")).toBeInTheDocument();
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("renders Inactive pill when is_active=false", () => {
    render(<TemplateRow template={INACTIVE_TEMPLATE} href="/templates/cust-2" />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
    expect(screen.getByText("Custom")).toBeInTheDocument();
  });

  it("href attribute correct", () => {
    render(<TemplateRow template={SYSTEM_TEMPLATE} href="/templates/sys-1" />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/templates/sys-1");
  });
});
