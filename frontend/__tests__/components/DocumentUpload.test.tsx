/**
 * Tests for DocumentUpload component.
 *
 * Tests the consent toast display logic after upload — this is
 * security-critical because it warns users about §7216 requirements.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

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

// Mock Clerk
vi.mock("@clerk/nextjs", () => ({
  useAuth: () => ({
    getToken: vi.fn().mockResolvedValue("mock-token"),
  }),
}));

// Track API calls
const mockUpload = vi.fn();
const mockGetStatus = vi.fn();

vi.mock("@/lib/api", () => ({
  createDocumentsApi: () => ({
    upload: mockUpload,
  }),
  createConsentApi: () => ({
    getStatus: mockGetStatus,
  }),
}));

import DocumentUpload from "@/components/documents/DocumentUpload";

describe("DocumentUpload", () => {
  const onUploaded = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUpload.mockResolvedValue({
      id: "doc-1",
      filename: "test.pdf",
      status: "uploaded",
    });
  });

  it("renders the upload area", () => {
    render(<DocumentUpload clientId="client-1" onUploaded={onUploaded} />);
    expect(screen.getByText(/drop a file here/i)).toBeInTheDocument();
    expect(screen.getByText(/click to browse/i)).toBeInTheDocument();
  });

  it("shows consent toast for determination_needed after upload", async () => {
    mockGetStatus.mockResolvedValue({
      has_tax_documents: true,
      consent_status: "determination_needed",
    });

    render(<DocumentUpload clientId="client-toast-1" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "tax-return.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/tax document detected/i)).toBeInTheDocument();
      expect(screen.getByText(/set up now/i)).toBeInTheDocument();
    });
  });

  it("shows consent toast for pending status after upload", async () => {
    mockGetStatus.mockResolvedValue({
      has_tax_documents: true,
      consent_status: "pending",
    });

    render(<DocumentUpload clientId="client-toast-2" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "1040.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/tax document detected/i)).toBeInTheDocument();
      expect(screen.getByText(/section 7216 consent/i)).toBeInTheDocument();
    });
  });

  it("does NOT show consent toast when consent is obtained", async () => {
    mockGetStatus.mockResolvedValue({
      has_tax_documents: true,
      consent_status: "obtained",
    });

    render(<DocumentUpload clientId="client-toast-3" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "w2.pdf", { type: "application/pdf" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalled();
    });

    expect(screen.queryByText(/tax document detected/i)).not.toBeInTheDocument();
  });

  it("does NOT show consent toast when no tax documents", async () => {
    mockGetStatus.mockResolvedValue({
      has_tax_documents: false,
      consent_status: "not_required",
    });

    render(<DocumentUpload clientId="client-toast-4" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "notes.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalled();
    });

    expect(screen.queryByText(/tax document detected/i)).not.toBeInTheDocument();
  });

  it("shows error message on upload failure", async () => {
    mockUpload.mockRejectedValue(new Error("Upload failed: file too large"));

    render(<DocumentUpload clientId="client-err" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["x".repeat(100)], "big.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(
        screen.getByText(/upload failed: file too large/i)
      ).toBeInTheDocument();
    });
  });

  it("shows upgrade link when document limit error", async () => {
    mockUpload.mockRejectedValue(
      new Error("Document limit reached for this plan")
    );

    render(<DocumentUpload clientId="client-limit" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "doc.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText(/upgrade your plan/i)).toBeInTheDocument();
    });
  });

  it("calls onUploaded callback after successful upload", async () => {
    const uploadedDoc = { id: "doc-new", filename: "result.pdf" };
    mockUpload.mockResolvedValue(uploadedDoc);
    mockGetStatus.mockResolvedValue({
      has_tax_documents: false,
      consent_status: "not_required",
    });

    render(<DocumentUpload clientId="client-cb" onUploaded={onUploaded} />);

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "result.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalledWith(uploadedDoc);
    });
  });
});
