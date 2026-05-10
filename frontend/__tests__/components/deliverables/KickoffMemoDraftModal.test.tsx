import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";

const stableGetToken = vi.fn().mockResolvedValue("test-token");

// Mock Clerk
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

// Mock OrgContext
vi.mock("@/contexts/OrgContext", () => ({
  useOrg: () => ({
    activeOrg: { id: "org-1", role: "admin", org_type: "firm" },
    isAdmin: true,
  }),
}));

// Mock deliverables API
const mockDraftKickoffMemo = vi.fn();
const mockSendKickoffMemo = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return {
    ...actual,
    createDeliverablesApi: () => ({
      draftKickoffMemo: mockDraftKickoffMemo,
      sendKickoffMemo: mockSendKickoffMemo,
    }),
  };
});

import KickoffMemoDraftModal from "@/components/deliverables/KickoffMemoDraftModal";

const MOCK_DRAFT = {
  subject: "Engagement kickoff — Test Client — 2026",
  body: "Dear Test Client, here is your kickoff memo.",
  references: {
    strategies: [{ id: "s1", name: "Augusta Rule" }],
    tasks: [
      {
        id: "t1",
        name: "Get appraisal",
        owner_role: "client",
        due_date: "2026-06-15",
        strategy_name: "Augusta Rule",
      },
    ],
  },
  warnings: [],
};

beforeEach(() => {
  mockDraftKickoffMemo.mockReset();
  mockSendKickoffMemo.mockReset();
});

describe("KickoffMemoDraftModal", () => {
  it("renders 'Generating draft...' state immediately on mount", () => {
    // Never-resolving promise keeps loading state
    mockDraftKickoffMemo.mockReturnValue(new Promise(() => {}));

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={vi.fn()}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    expect(screen.getByText("Generating draft...")).toBeInTheDocument();
    // Subject label should not be visible yet
    expect(screen.queryByText("Subject")).toBeNull();
  });

  it("renders editable state with subject + body + chip lists when draft resolves", async () => {
    mockDraftKickoffMemo.mockResolvedValue(MOCK_DRAFT);

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={vi.fn()}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue(MOCK_DRAFT.subject)).toBeInTheDocument();
    });

    // Body textarea
    expect(screen.getByDisplayValue(MOCK_DRAFT.body)).toBeInTheDocument();
    // Strategy chip (also appears in task row as strategy_name)
    expect(screen.getAllByText("Augusta Rule").length).toBeGreaterThanOrEqual(1);
    // Task chip
    expect(screen.getByText("Get appraisal")).toBeInTheDocument();
    // Recipient email pre-filled
    expect(screen.getByDisplayValue("test@example.com")).toBeInTheDocument();
  });

  it("renders warnings banner when API returns non-empty warnings array", async () => {
    mockDraftKickoffMemo.mockResolvedValue({
      ...MOCK_DRAFT,
      warnings: ["No recommended strategies found"],
    });

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={vi.fn()}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("No recommended strategies found")).toBeInTheDocument();
    });
  });

  it("renders error state with retry CTA when draft fetch fails", async () => {
    mockDraftKickoffMemo.mockRejectedValueOnce(new Error("Network error"));

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={vi.fn()}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Failed to generate draft. Please try again.")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();

    // Click Retry triggers a second call
    mockDraftKickoffMemo.mockResolvedValue(MOCK_DRAFT);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(mockDraftKickoffMemo).toHaveBeenCalledTimes(2);
  });

  it("calls sendKickoffMemo on Send and closes on success", async () => {
    mockDraftKickoffMemo.mockResolvedValue(MOCK_DRAFT);
    mockSendKickoffMemo.mockResolvedValue({ client_communication_id: "ccid-1" });
    const onClose = vi.fn();

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={onClose}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    // Wait for draft to load
    await waitFor(() => {
      expect(screen.getByDisplayValue(MOCK_DRAFT.subject)).toBeInTheDocument();
    });

    // Edit subject via fireEvent
    const subjectInput = screen.getByDisplayValue(MOCK_DRAFT.subject);
    fireEvent.change(subjectInput, { target: { value: "Edited Subject" } });

    // Click Send
    fireEvent.click(screen.getByRole("button", { name: /send email/i }));

    await waitFor(() => {
      expect(mockSendKickoffMemo).toHaveBeenCalledWith("c1", {
        tax_year: new Date().getFullYear(),
        subject: "Edited Subject",
        body: MOCK_DRAFT.body,
        recipient_email: "test@example.com",
      });
    });

    // Toast appears
    await waitFor(() => {
      expect(screen.getByText("Kickoff memo sent successfully")).toBeInTheDocument();
    });

    // onClose called after timeout
    await waitFor(() => {
      expect(onClose).toHaveBeenCalled();
    }, { timeout: 2000 });
  });

  it("renders failure toast and keeps modal open on send rejection", async () => {
    mockDraftKickoffMemo.mockResolvedValue(MOCK_DRAFT);
    mockSendKickoffMemo.mockRejectedValueOnce(new Error("Send failed"));
    const onClose = vi.fn();

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={onClose}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    // Wait for draft to load
    await waitFor(() => {
      expect(screen.getByDisplayValue(MOCK_DRAFT.subject)).toBeInTheDocument();
    });

    // Click Send
    fireEvent.click(screen.getByRole("button", { name: /send email/i }));

    // Failure toast renders
    await waitFor(() => {
      expect(
        screen.getByText(/Failed to send\. Please try again or check the recipient address\./)
      ).toBeInTheDocument();
    });

    // Modal still open (subject input present)
    expect(screen.getByDisplayValue(MOCK_DRAFT.subject)).toBeInTheDocument();

    // onClose not called
    expect(onClose).not.toHaveBeenCalled();

    // Send button re-enabled
    const sendBtn = screen.getByRole("button", { name: /send email/i });
    expect(sendBtn).not.toBeDisabled();
  });

  it("Cancel closes modal without calling sendKickoffMemo", async () => {
    mockDraftKickoffMemo.mockResolvedValue(MOCK_DRAFT);
    const onClose = vi.fn();

    render(
      <KickoffMemoDraftModal
        open={true}
        onClose={onClose}
        clientId="c1"
        clientName="Test Client"
        clientEmail="test@example.com"
      />
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue(MOCK_DRAFT.subject)).toBeInTheDocument();
    });

    // The footer Cancel button (not the X close button)
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(mockSendKickoffMemo).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
