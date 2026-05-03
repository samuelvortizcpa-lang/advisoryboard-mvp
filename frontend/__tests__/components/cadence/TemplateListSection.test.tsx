import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import type { CadenceTemplateSummary } from "@/lib/api";
import TemplateListSection from "@/components/cadence/TemplateListSection";

const TEMPLATES: CadenceTemplateSummary[] = [
  { id: "sys-1", name: "Full Cadence", description: "All 7", is_system: true, is_active: true },
  { id: "sys-2", name: "Empty", description: null, is_system: true, is_active: true },
];

describe("TemplateListSection", () => {
  it("renders section title", () => {
    render(
      <TemplateListSection title="System templates" templates={TEMPLATES} basePath="/base" />,
    );
    expect(screen.getByText("System templates")).toBeInTheDocument();
  });

  it("renders templates as rows", () => {
    render(
      <TemplateListSection title="System templates" templates={TEMPLATES} basePath="/base" />,
    );
    expect(screen.getByText("Full Cadence")).toBeInTheDocument();
    expect(screen.getByText("Empty")).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute("href", "/base/sys-1");
    expect(links[1]).toHaveAttribute("href", "/base/sys-2");
  });

  it("renders emptyMessage when templates is empty AND emptyMessage provided", () => {
    render(
      <TemplateListSection
        title="Custom"
        templates={[]}
        basePath="/base"
        emptyMessage="No custom templates yet."
      />,
    );
    expect(screen.getByText("No custom templates yet.")).toBeInTheDocument();
  });

  it("renders nothing for empty list when no emptyMessage", () => {
    const { container } = render(
      <TemplateListSection title="Custom" templates={[]} basePath="/base" />,
    );
    expect(screen.getByText("Custom")).toBeInTheDocument();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    // No empty message paragraph
    expect(container.querySelector("p")).toBeNull();
  });
});
