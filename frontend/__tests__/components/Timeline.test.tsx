import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

const stableGetToken = vi.fn().mockResolvedValue("test-token");

// Mock Clerk
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

// Mock timeline API
const mockList = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createTimelineApi: () => ({ list: mockList }),
  };
});

import Timeline from "@/components/timeline/Timeline";

function makeCommItem(overrides: Record<string, unknown> = {}) {
  return {
    type: "communication" as const,
    id: "comm-1",
    date: new Date().toISOString(),
    title: "Email sent: Test Subject",
    subtitle: "To client@example.com",
    icon_hint: "email",
    status: "sent",
    metadata: { communication_id: "c1", ai_drafted: false },
    ...overrides,
  };
}

describe("Timeline CommunicationCard status badges", () => {
  it("renders bounced badge for status=bounced", async () => {
    mockList.mockResolvedValue({
      items: [makeCommItem({ status: "bounced" })],
      total: 1,
    });

    render(<Timeline clientId="client-1" />);

    await waitFor(() => {
      expect(screen.getByText("bounced")).toBeInTheDocument();
    });
  });

  it("renders failed badge for status=failed", async () => {
    mockList.mockResolvedValue({
      items: [makeCommItem({ status: "failed" })],
      total: 1,
    });

    render(<Timeline clientId="client-1" />);

    await waitFor(() => {
      expect(screen.getByText("failed")).toBeInTheDocument();
    });
  });

  it("does not render badge for status=sent", async () => {
    mockList.mockResolvedValue({
      items: [makeCommItem({ status: "sent" })],
      total: 1,
    });

    render(<Timeline clientId="client-1" />);

    await waitFor(() => {
      expect(screen.getByText("Email sent: Test Subject")).toBeInTheDocument();
    });

    // No status badge for "sent"
    expect(screen.queryByText("sent")).toBeNull();
  });
});
