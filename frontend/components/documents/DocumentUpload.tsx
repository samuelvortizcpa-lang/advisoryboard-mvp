"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Document, createConsentApi, createDocumentsApi } from "@/lib/api";

interface Props {
  clientId: string;
  onUploaded: (doc: Document) => void;
}

// Track which clients have already shown the consent toast this session
const consentToastShown = new Set<string>();

export default function DocumentUpload({ clientId, onUploaded }: Props) {
  const { getToken } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);

  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [consentToast, setConsentToast] = useState(false);

  // Auto-dismiss consent toast after 10 seconds
  useEffect(() => {
    if (!consentToast) return;
    const t = setTimeout(() => setConsentToast(false), 10000);
    return () => clearTimeout(t);
  }, [consentToast]);

  async function uploadFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const doc = await createDocumentsApi(getToken).upload(clientId, file);
      onUploaded(doc);

      // Check if consent is now needed (one-time per client per session)
      if (!consentToastShown.has(clientId)) {
        try {
          const status = await createConsentApi(getToken).getStatus(clientId);
          if (status.has_tax_documents && status.consent_status === "pending") {
            consentToastShown.add(clientId);
            setConsentToast(true);
          }
        } catch {
          /* non-fatal */
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    uploadFile(files[0]);
  }

  return (
    <div>
      {/* Consent reminder toast */}
      {consentToast && (
        <div className="mb-3 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <svg
            className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          <div className="flex-1 text-sm text-amber-700">
            <span className="font-medium">Tax document detected</span> —
            Remember to obtain Section 7216 consent for this client before
            proceeding with AI analysis.{" "}
            <Link
              href={`/dashboard/clients/${clientId}?tab=overview`}
              className="font-medium underline hover:text-amber-900"
            >
              Generate Form
            </Link>
          </div>
          <button
            onClick={() => setConsentToast(false)}
            className="shrink-0 rounded p-0.5 text-amber-400 hover:text-amber-600"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => !uploading && inputRef.current?.click()}
        className={[
          "flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-blue-400 bg-blue-50" : "border-gray-300 bg-white hover:border-gray-400",
          uploading ? "cursor-not-allowed opacity-60" : "cursor-pointer",
        ].join(" ")}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
          disabled={uploading}
        />

        {uploading ? (
          <>
            <div className="h-6 w-6 rounded-full border-2 border-blue-600 border-t-transparent animate-spin" />
            <p className="mt-2 text-sm text-gray-500">Uploading…</p>
          </>
        ) : (
          <>
            <UploadIcon />
            <p className="mt-2 text-sm font-medium text-gray-700">
              Drop a file here, or{" "}
              <span className="text-blue-600">click to browse</span>
            </p>
            <p className="mt-1 text-xs text-gray-400">
              PDF, DOCX, XLSX, images, and more
            </p>
          </>
        )}
      </div>

      {error && (
        <div className="mt-2 text-sm text-red-600">
          {error}
          {error.toLowerCase().includes("document limit") && (
            <a
              href="/dashboard/settings/subscriptions"
              className="ml-2 font-medium text-blue-600 underline hover:text-blue-700"
            >
              Upgrade your plan
            </a>
          )}
          {error.toLowerCase().includes("already exists") && (
            <p className="mt-1 text-xs text-gray-500">
              Delete the existing version first if you want to re-upload.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function UploadIcon() {
  return (
    <svg
      className="h-8 w-8 text-gray-400"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
      />
    </svg>
  );
}
