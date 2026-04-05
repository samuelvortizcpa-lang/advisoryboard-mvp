"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useRef, useState } from "react";

import { createDocumentsApi } from "@/lib/api";

interface Props {
  onNext: () => void;
  onSkip: () => void;
  clientId: string | null;
  clientName: string | null;
  onDocUploaded: (documentId: string) => void;
}

const ACCEPT =
  ".pdf,.docx,.doc,.png,.jpg,.jpeg,.xlsx,.csv,.msg,.eml,.txt,.rtf";

export default function UploadDocStep({
  onNext,
  onSkip,
  clientId,
  clientName,
  onDocUploaded,
}: Props) {
  const { getToken } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [uploading, setUploading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = useCallback(
    async (file: File) => {
      if (!clientId) return;
      setUploading(true);
      setError(null);

      try {
        const api = createDocumentsApi(getToken);
        const doc = await api.upload(clientId, file);
        onDocUploaded(doc.id);
        setSuccess(true);
        setTimeout(() => onNext(), 2000);
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "Upload failed. Please try again."
        );
      } finally {
        setUploading(false);
      }
    },
    [clientId, getToken, onDocUploaded, onNext]
  );

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  // No client — prompt to go back
  if (!clientId) {
    return (
      <div className="w-full max-w-md text-center">
        <p className="text-xs font-medium uppercase tracking-widest text-gray-400">
          Step 2 of 3
        </p>
        <h2 className="mt-2 text-2xl font-semibold text-gray-900">
          Upload a document
        </h2>
        <p className="mt-2 text-sm text-gray-500">
          Add a client first to upload documents.
        </p>
        <button
          onClick={onSkip}
          className="mt-6 rounded-lg bg-gray-900 px-8 py-3 text-sm font-medium text-white transition hover:bg-gray-800"
        >
          Continue &rarr;
        </button>
      </div>
    );
  }

  return (
    <div className="w-full max-w-md">
      <p className="text-xs font-medium uppercase tracking-widest text-gray-400">
        Step 2 of 3
      </p>
      <h2 className="mt-2 text-2xl font-semibold text-gray-900">
        Upload a document
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        Add a document for {clientName}. Tax returns, engagement letters,
        financials — anything works.
      </p>
      <p className="mt-1 text-xs text-gray-400">
        Supports PDF, DOCX, images, and more
      </p>

      {/* Upload zone */}
      <div className="mt-6">
        {success ? (
          <div className="flex flex-col items-center rounded-xl border-2 border-green-200 bg-green-50 p-8 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
              <svg
                className="h-6 w-6 text-green-600"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth={2.5}
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </div>
            <p className="mt-3 text-sm font-medium text-green-800">
              Document uploaded!
            </p>
            <p className="mt-1 text-xs text-green-600">
              Callwen is processing it now.
            </p>
          </div>
        ) : uploading ? (
          <div className="flex flex-col items-center rounded-xl border-2 border-dashed border-gray-300 p-8">
            <p className="text-sm text-gray-500">Uploading…</p>
            <div className="mt-3 h-1.5 w-48 overflow-hidden rounded-full bg-gray-200">
              <div className="h-full w-1/2 animate-pulse rounded-full bg-gray-900" />
            </div>
          </div>
        ) : (
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex cursor-pointer flex-col items-center rounded-xl border-2 border-dashed p-8 text-center transition ${
              dragOver
                ? "border-gray-900 bg-gray-50"
                : "border-gray-300 hover:border-gray-400"
            }`}
          >
            <svg
              className="h-10 w-10 text-gray-300"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
              <path d="M12 12v9" />
              <path d="m16 16-4-4-4 4" />
            </svg>
            <p className="mt-3 text-sm text-gray-500">
              Drag &amp; drop a file here, or click to browse
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              onChange={handleFileChange}
              className="hidden"
            />
          </div>
        )}
      </div>

      {/* Error */}
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {/* Skip */}
      {!success && (
        <button
          onClick={onSkip}
          disabled={uploading}
          className="mt-4 w-full py-2 text-sm text-gray-500 transition-colors hover:text-gray-700 disabled:opacity-50"
        >
          Skip — I&apos;ll upload later
        </button>
      )}
    </div>
  );
}
