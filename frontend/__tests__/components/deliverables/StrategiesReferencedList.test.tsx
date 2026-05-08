import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import StrategiesReferencedList from "@/components/deliverables/StrategiesReferencedList";

describe("StrategiesReferencedList", () => {
  it("renders empty state when strategies is empty", () => {
    render(<StrategiesReferencedList strategies={[]} />);
    expect(screen.getByText("No strategies referenced.")).toBeInTheDocument();
  });

  it("renders one chip per strategy", () => {
    render(
      <StrategiesReferencedList
        strategies={[
          { id: "s1", name: "Augusta Rule" },
          { id: "s2", name: "Cost Segregation" },
        ]}
      />
    );
    expect(screen.getByText("Augusta Rule")).toBeInTheDocument();
    expect(screen.getByText("Cost Segregation")).toBeInTheDocument();
    expect(screen.getByText("Strategies referenced (2):")).toBeInTheDocument();
  });
});
