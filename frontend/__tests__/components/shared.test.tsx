/**
 * Tests for dashboard shared components and constants.
 *
 * Verifies that dashboard data display logic, tier badges, and
 * attention card formatting work correctly.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

// Mock next/link
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) => <a href={href}>{children}</a>,
}));

// Mock UI components
vi.mock("@/components/ui/SectionCard", () => ({
  default: ({
    children,
    title,
  }: {
    children: React.ReactNode;
    title: string;
  }) => (
    <div data-testid={`section-${title}`}>
      <h3>{title}</h3>
      {children}
    </div>
  ),
}));

vi.mock("@/components/ui/PriorityDot", () => ({
  default: ({ priority }: { priority: string }) => (
    <span data-testid={`dot-${priority}`} />
  ),
}));

vi.mock("@/components/ui/ThinProgress", () => ({
  default: ({
    label,
    current,
    max,
  }: {
    label: string;
    current: number;
    max: number;
  }) => (
    <div data-testid={`progress-${label}`}>
      {current}/{max}
    </div>
  ),
}));

import {
  RANGE_DAYS,
  DIST_COLORS,
  TIER_BADGE_COLORS,
  AttentionCard,
  RecentClientsCard,
  UsageCard,
  DashboardSkeleton,
} from "@/components/dashboard/shared";
import type { DashboardSummary } from "@/lib/api";

// ─── Constants tests ────────────────────────────────────────────────────────

describe("RANGE_DAYS", () => {
  it("maps time ranges to correct day counts", () => {
    expect(RANGE_DAYS["7d"]).toBe(7);
    expect(RANGE_DAYS["30d"]).toBe(30);
    expect(RANGE_DAYS["90d"]).toBe(90);
  });
});

describe("DIST_COLORS", () => {
  it("has colors for all query types", () => {
    expect(DIST_COLORS["Document lookups"]).toBeDefined();
    expect(DIST_COLORS["Advanced analyses"]).toBeDefined();
    expect(DIST_COLORS["Premium analyses"]).toBeDefined();
    expect(DIST_COLORS.Briefs).toBeDefined();
    expect(DIST_COLORS.Other).toBeDefined();
  });
});

describe("TIER_BADGE_COLORS", () => {
  it("has badge styles for all tiers", () => {
    expect(TIER_BADGE_COLORS.firm).toContain("indigo");
    expect(TIER_BADGE_COLORS.professional).toContain("purple");
    expect(TIER_BADGE_COLORS.starter).toContain("blue");
    expect(TIER_BADGE_COLORS.free).toContain("gray");
  });
});

// ─── Component tests ────────────────────────────────────────────────────────

function makeDashboardData(
  overrides: Partial<DashboardSummary> = {}
): DashboardSummary {
  return {
    stats: {
      clients: { count: 5, limit: 10 },
      documents: { count: 20, limit: 100 },
      ai_queries: { used: 50, limit: 200 },
      action_items: { open: 3, completed: 7 },
    },
    plan: {
      tier: "starter",
      billing_interval: "month",
      seats_used: 2,
      seats_total: 5,
    },
    attention_items: [],
    recent_clients: [],
    activity: [],
    query_distribution: [],
    team: [],
    ...overrides,
  } as DashboardSummary;
}

describe("AttentionCard", () => {
  it("shows 'All caught up' when no attention items", () => {
    render(<AttentionCard data={makeDashboardData()} />);
    expect(screen.getByText("All caught up")).toBeInTheDocument();
  });

  it("renders attention items with descriptions", () => {
    const data = makeDashboardData({
      attention_items: [
        {
          id: "1",
          description: "Review tax return",
          client_name: "Alice Corp",
          client_id: "c-1",
          priority: "critical",
          due_date: null,
          overdue_days: null,
        },
      ],
    });
    render(<AttentionCard data={data} />);
    expect(screen.getByText("Review tax return")).toBeInTheDocument();
    expect(screen.getByText(/Alice Corp/)).toBeInTheDocument();
  });

  it("shows overdue label for overdue items", () => {
    const data = makeDashboardData({
      attention_items: [
        {
          id: "2",
          description: "File extension",
          client_name: "Bob LLC",
          client_id: "c-2",
          priority: "warning",
          due_date: null,
          overdue_days: 3,
        },
      ],
    });
    render(<AttentionCard data={data} />);
    expect(screen.getByText(/overdue by 3 days/i)).toBeInTheDocument();
  });

  it("limits display to 5 items", () => {
    const items = Array.from({ length: 8 }, (_, i) => ({
      id: String(i),
      description: `Item ${i}`,
      client_name: `Client ${i}`,
      client_id: `c-${i}`,
      priority: "info" as const,
      due_date: null,
      overdue_days: null,
    }));
    const data = makeDashboardData({ attention_items: items });
    render(<AttentionCard data={data} />);
    // Should show items 0-4 but not 5-7
    expect(screen.getByText("Item 0")).toBeInTheDocument();
    expect(screen.getByText("Item 4")).toBeInTheDocument();
    expect(screen.queryByText("Item 5")).not.toBeInTheDocument();
  });
});

describe("RecentClientsCard", () => {
  it("renders client links with initials", () => {
    const data = makeDashboardData({
      recent_clients: [
        {
          id: "c1",
          name: "Alice Corp",
          document_count: 3,
          action_item_count: 1,
          last_activity: "2025-03-15T12:00:00Z",
        },
      ],
    });
    render(<RecentClientsCard data={data} />);
    expect(screen.getByText("Alice Corp")).toBeInTheDocument();
    expect(screen.getByText("AC")).toBeInTheDocument();
    // Text is split across React text nodes, so check the parent element
    const clientRow = screen.getByText("Alice Corp").closest("a")!;
    expect(clientRow.textContent).toContain("3 document");
    expect(clientRow.textContent).toContain("1 action item");
  });

  it("pluralizes document and action item counts", () => {
    const data = makeDashboardData({
      recent_clients: [
        {
          id: "c2",
          name: "Test",
          document_count: 1,
          action_item_count: 0,
          last_activity: "2025-03-15T12:00:00Z",
        },
      ],
    });
    render(<RecentClientsCard data={data} />);
    const row = screen.getByText("Test").closest("a")!;
    expect(row.textContent).toContain("1 document");
    expect(row.textContent).toContain("0 action items");
  });
});

describe("UsageCard", () => {
  it("renders progress bars for usage stats", () => {
    render(<UsageCard data={makeDashboardData()} />);
    expect(screen.getByTestId("progress-Clients")).toBeInTheDocument();
    expect(screen.getByTestId("progress-Documents")).toBeInTheDocument();
    expect(screen.getByTestId("progress-AI Queries")).toBeInTheDocument();
  });

  it("shows tier badge", () => {
    render(<UsageCard data={makeDashboardData()} />);
    expect(screen.getByText("Starter")).toBeInTheDocument();
  });

  it("shows upgrade link for free tier", () => {
    const data = makeDashboardData({
      plan: { tier: "free", billing_interval: null, seats_used: 1, seats_total: 1 },
    });
    render(<UsageCard data={data} />);
    expect(screen.getByText("Upgrade")).toBeInTheDocument();
  });

  it("hides upgrade link for firm tier", () => {
    const data = makeDashboardData({
      plan: { tier: "firm", billing_interval: "month", seats_used: 3, seats_total: 10 },
    });
    render(<UsageCard data={data} />);
    expect(screen.queryByText("Upgrade")).not.toBeInTheDocument();
  });

  it("shows seat count when showSeats is true", () => {
    render(<UsageCard data={makeDashboardData()} showSeats />);
    expect(screen.getByText(/2 of 5 seats/)).toBeInTheDocument();
  });
});

describe("DashboardSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<DashboardSkeleton />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
  });
});
