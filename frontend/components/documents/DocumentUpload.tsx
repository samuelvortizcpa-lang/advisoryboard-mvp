"use client";

import { useAuth } from "@clerk/nextjs";
import { useRef, useState } from "react";

import { Document, createDocumentsApi } from "@/lib/api";

interface Props {
  clientId: string;
  onUploaded: (doc: Document) => void;
}

export default function DocumentUpload({ clientId, onUploaded }: Props) {
  const { getToken } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);

  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function uploadFile(file: File) {
    setUploading(true);
    setError(null);
    try {
      const doc = await createDocumentsApi(getToken).upload(clientId, file);
      onUploaded(doc);
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
