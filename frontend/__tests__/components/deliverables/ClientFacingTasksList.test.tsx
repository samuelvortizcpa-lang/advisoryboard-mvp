import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import ClientFacingTasksList from "@/components/deliverables/ClientFacingTasksList";

describe("ClientFacingTasksList", () => {
  it("renders empty state when tasks is empty", () => {
    render(<ClientFacingTasksList tasks={[]} />);
    expect(screen.getByText("No client-facing tasks referenced.")).toBeInTheDocument();
  });

  it("renders chip per task with owner_role and due_date", () => {
    render(
      <ClientFacingTasksList
        tasks={[
          {
            id: "t1",
            name: "Get appraisal",
            owner_role: "client",
            due_date: "2026-06-15",
            strategy_name: "Cost Seg",
          },
        ]}
      />
    );
    expect(screen.getByText("Get appraisal")).toBeInTheDocument();
    expect(screen.getByText("client")).toBeInTheDocument();
    expect(screen.getByText("2026-06-15")).toBeInTheDocument();
    expect(screen.getByText("Cost Seg")).toBeInTheDocument();
    expect(screen.getByText("Client-facing tasks (1):")).toBeInTheDocument();
  });
});
