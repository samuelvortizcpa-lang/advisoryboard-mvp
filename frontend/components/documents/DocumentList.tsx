"use client";

import { Document } from "@/lib/api";

interface Props {
  documents: Document[];
  onDownload: (doc: Document) => void;
  onDelete: (doc: Document) => void;
  downloading: string | null; // document id currently being downloaded
  deleting: string | null;    // document id currently being deleted
  // Selection mode (optional — omit to hide checkboxes)
  selectedIds?: Set<string>;
  onToggleSelect?: (id: string) => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

export default function DocumentList({
  documents,
  onDownload,
  onDelete,
  downloading,
  deleting,
  selectedIds,
  onToggleSelect,
  loading,
  error,
  onRetry,
}: Props) {
  const selectable = selectedIds !== undefined && onToggleSelect !== undefined;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-400">
        <svg className="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
        Loading...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-between px-4 py-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm">
        <span>{error}</span>
        {onRetry && <button onClick={onRetry} className="text-red-500 underline text-xs">Retry</button>}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center">
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gray-100">
          <DocumentEmptyIcon />
        </div>
        <p className="text-sm text-gray-500">No documents yet — upload your first document to get started</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-gray-100">
      {documents.map((doc) => {
        const isDownloading = downloading === doc.id;
        const isDeleting = deleting === doc.id;
        const busy = isDownloading || isDeleting;
        const isSelected = selectable && selectedIds.has(doc.id);
        const canSelect = doc.processed;

        return (
          <li
            key={doc.id}
            className={[
              "flex items-center gap-3 py-3 px-1 transition-colors",
              isSelected ? "bg-blue-50" : "",
            ].join(" ")}
          >
            {/* Checkbox (only shown in selection mode) */}
            {selectable && (
              <input
                type="checkbox"
                checked={isSelected}
                disabled={!canSelect}
                onChange={() => canSelect && onToggleSelect(doc.id)}
                title={canSelect ? "Select for comparison" : "Document must be processed first"}
                className="h-4 w-4 shrink-0 accent-blue-600 cursor-pointer disabled:cursor-not-allowed disabled:opacity-40"
              />
            )}

            <FileIcon fileType={doc.file_type} />

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <p className="truncate text-sm font-medium text-gray-800">
                  {doc.filename}
                </p>
                {doc.amends_subtype ? (
                  <span
                    title={`Amends ${doc.amends_subtype}`}
                    className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-orange-200 bg-orange-50 px-1.5 py-0.5 text-[10px] font-medium leading-none text-orange-700"
                  >
                    <AmendmentIcon />
                    {doc.amendment_number && doc.amendment_number > 1
                      ? `Amendment #${doc.amendment_number}`
                      : "Amendment"}
                  </span>
                ) : doc.document_type && doc.document_type !== "other" ? (
                  <DocTypeBadge type={doc.document_type} subtype={doc.document_subtype} />
                ) : null}
                {doc.is_superseded && (
                  <span
                    title={doc.superseded_by ? "Superseded by a newer version" : "A newer version of this document exists"}
                    className="inline-flex items-center gap-0.5 rounded-full bg-amber-50 border border-amber-200 px-1.5 py-0.5 text-[10px] font-medium text-amber-700"
                  >
                    <SupersededIcon />
                    Superseded
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400">
                {formatBytes(doc.file_size)} ·{" "}
                {new Date(doc.upload_date).toLocaleDateString("en-US", {
                  year: "numeric",
                  month: "short",
                  day: "numeric",
                })}
                {doc.document_period && (
                  <span className="ml-1.5 text-gray-500">{doc.document_period}</span>
                )}
                {!doc.processed && (
                  <span className="ml-1.5 text-amber-500">(processing…)</span>
                )}
              </p>
            </div>

            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => onDownload(doc)}
                disabled={busy}
                title="Download"
                className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isDownloading ? (
                  <Spinner />
                ) : (
                  <DownloadIcon />
                )}
              </button>

              <button
                onClick={() => onDelete(doc)}
                disabled={busy}
                title="Delete"
                className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {isDeleting ? (
                  <Spinner className="text-red-500" />
                ) : (
                  <TrashIcon />
                )}
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function DocumentEmptyIcon() {
  return (
    <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
    </svg>
  );
}

// file_type is a short extension string from the backend: "pdf", "docx", "jpg", etc.
function FileIcon({ fileType }: { fileType: string }) {
  const isPdf = fileType === "pdf";
  const isImage = ["jpg", "jpeg", "png", "gif", "webp", "svg"].includes(fileType);

  const color = isPdf
    ? "text-red-400"
    : isImage
    ? "text-purple-400"
    : "text-blue-400";

  return (
    <svg
      className={`h-8 w-8 shrink-0 ${color}`}
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
      />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"
      />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      className="h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"
      />
    </svg>
  );
}

function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`block h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin ${className}`}
    />
  );
}

const DOC_TYPE_COLORS: Record<string, string> = {
  tax_return: "bg-red-50 text-red-700 border-red-200",
  w2: "bg-red-50 text-red-700 border-red-200",
  k1: "bg-red-50 text-red-700 border-red-200",
  financial_statement: "bg-green-50 text-green-700 border-green-200",
  bank_statement: "bg-green-50 text-green-700 border-green-200",
  engagement_letter: "bg-blue-50 text-blue-700 border-blue-200",
  contract: "bg-blue-50 text-blue-700 border-blue-200",
  meeting_notes: "bg-purple-50 text-purple-700 border-purple-200",
  email: "bg-gray-50 text-gray-600 border-gray-200",
  invoice: "bg-amber-50 text-amber-700 border-amber-200",
  receipt: "bg-amber-50 text-amber-700 border-amber-200",
};

const DOC_TYPE_LABELS: Record<string, string> = {
  tax_return: "Tax Return",
  w2: "W-2",
  k1: "K-1",
  financial_statement: "Financial",
  bank_statement: "Bank Stmt",
  engagement_letter: "Engagement",
  contract: "Contract",
  meeting_notes: "Notes",
  email: "Email",
  invoice: "Invoice",
  receipt: "Receipt",
};

function DocTypeBadge({ type, subtype }: { type: string; subtype: string | null }) {
  const colors = DOC_TYPE_COLORS[type] ?? "bg-gray-50 text-gray-600 border-gray-200";
  const label = subtype || DOC_TYPE_LABELS[type] || type;

  return (
    <span className={`inline-flex shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-medium leading-none ${colors}`}>
      {label}
    </span>
  );
}

function AmendmentIcon() {
  return (
    <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
    </svg>
  );
}

function SupersededIcon() {
  return (
    <svg className="h-2.5 w-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
    </svg>
  );
}
