"use client";

import { useEffect, useRef, useState } from "react";
import { ClientBrief } from "@/lib/api";

interface Props {
  brief: ClientBrief;
  onClose: () => void;
}

export default function BriefPanel({ brief, onClose }: Props) {
  const [copied, setCopied] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(brief.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback
      const textarea = document.createElement("textarea");
      textarea.value = brief.content;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function handleExportPdf() {
    // Create a printable window with the brief content
    const printWindow = window.open("", "_blank");
    if (!printWindow) return;

    const htmlContent = markdownToHtml(brief.content);
    const generatedDate = new Date(brief.generated_at).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>Client Brief</title>
        <style>
          body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px; color: #1a1a1a; }
          h1 { font-size: 22px; border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 20px; }
          h2 { font-size: 16px; margin-top: 24px; margin-bottom: 8px; color: #1e40af; }
          h3 { font-size: 14px; margin-top: 16px; margin-bottom: 6px; }
          p { font-size: 13px; line-height: 1.6; margin: 8px 0; }
          ul { font-size: 13px; line-height: 1.6; padding-left: 20px; }
          li { margin: 4px 0; }
          strong { font-weight: 600; }
          hr { border: none; border-top: 1px solid #e5e7eb; margin: 16px 0; }
          .meta { font-size: 11px; color: #6b7280; margin-bottom: 20px; }
          @media print { body { padding: 20px; } }
        </style>
      </head>
      <body>
        <h1>Client Meeting Brief</h1>
        <div class="meta">Generated on ${generatedDate} · ${brief.document_count ?? 0} documents · ${brief.action_item_count ?? 0} action items</div>
        ${htmlContent}
      </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.print();
  }

  const generatedDate = new Date(brief.generated_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over panel */}
      <div
        ref={panelRef}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col bg-white shadow-2xl animate-slide-in-right"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Meeting Brief</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {generatedDate} · {brief.document_count ?? 0} docs · {brief.action_item_count ?? 0} actions
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              title="Copy to clipboard"
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
            >
              {copied ? (
                <>
                  <CheckIcon />
                  Copied
                </>
              ) : (
                <>
                  <CopyIcon />
                  Copy
                </>
              )}
            </button>
            <button
              onClick={handleExportPdf}
              title="Export as PDF"
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 transition-colors hover:bg-gray-50"
            >
              <PdfIcon />
              PDF
            </button>
            <button
              onClick={onClose}
              title="Close"
              className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            >
              <CloseIcon />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <div className="prose-sm text-gray-700">
            <MarkdownRenderer content={brief.content} />
          </div>
        </div>

        {/* Footer metadata */}
        {brief.metadata_ && (
          <div className="border-t border-gray-100 px-6 py-3 text-[10px] text-gray-400">
            Generated by {(brief.metadata_.model as string) ?? "GPT-4o"} in{" "}
            {(brief.metadata_.generation_time_seconds as number)?.toFixed(1) ?? "—"}s ·{" "}
            {(brief.metadata_.total_tokens as number) ?? 0} tokens
          </div>
        )}
      </div>
    </>
  );
}

// ─── Lightweight Markdown renderer ────────────────────────────────────────────

function MarkdownRenderer({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") {
      i++;
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={i} className="my-4 border-gray-200" />);
      i++;
      continue;
    }

    if (line.startsWith("## ")) {
      elements.push(
        <h2 key={i} className="mt-5 mb-2 text-sm font-semibold text-gray-900 first:mt-0">
          {line.slice(3)}
        </h2>
      );
      i++;
      continue;
    }

    if (line.startsWith("### ")) {
      elements.push(
        <h3 key={i} className="mt-4 mb-1.5 text-sm font-semibold text-gray-800 first:mt-0">
          {line.slice(4)}
        </h3>
      );
      i++;
      continue;
    }

    // Numbered list
    if (/^\d+\.\s/.test(line.trimStart())) {
      const listItems: React.ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trimStart())) {
        const itemText = lines[i].trimStart().replace(/^\d+\.\s/, "");
        listItems.push(
          <li key={i} className="leading-relaxed">
            <InlineMarkdown text={itemText} />
          </li>
        );
        i++;
      }
      elements.push(
        <ol key={`ol-${i}`} className="my-2 ml-4 list-decimal space-y-1 text-sm">
          {listItems}
        </ol>
      );
      continue;
    }

    // Bullet list
    if (line.trimStart().startsWith("- ") || line.trimStart().startsWith("* ")) {
      const listItems: React.ReactNode[] = [];
      while (
        i < lines.length &&
        (lines[i].trimStart().startsWith("- ") || lines[i].trimStart().startsWith("* "))
      ) {
        const itemText = lines[i].trimStart().slice(2);
        listItems.push(
          <li key={i} className="leading-relaxed">
            <InlineMarkdown text={itemText} />
          </li>
        );
        i++;
      }
      elements.push(
        <ul key={`ul-${i}`} className="my-2 ml-4 list-disc space-y-1 text-sm">
          {listItems}
        </ul>
      );
      continue;
    }

    // Paragraph
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("## ") &&
      !lines[i].startsWith("### ") &&
      !/^---+$/.test(lines[i].trim()) &&
      !lines[i].trimStart().startsWith("- ") &&
      !lines[i].trimStart().startsWith("* ") &&
      !/^\d+\.\s/.test(lines[i].trimStart())
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    if (paraLines.length > 0) {
      elements.push(
        <p key={`p-${i}`} className="my-2 text-sm leading-relaxed">
          <InlineMarkdown text={paraLines.join(" ")} />
        </p>
      );
    }
  }

  return <>{elements}</>;
}

function InlineMarkdown({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return (
    <>
      {parts.map((part, idx) => {
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={idx}>{part.slice(2, -2)}</strong>;
        }
        if (part.startsWith("*") && part.endsWith("*")) {
          return <em key={idx}>{part.slice(1, -1)}</em>;
        }
        return <span key={idx}>{part}</span>;
      })}
    </>
  );
}

// Simple markdown-to-HTML for PDF export
function markdownToHtml(md: string): string {
  return md
    .split("\n")
    .map((line) => {
      if (line.trim() === "") return "";
      if (/^---+$/.test(line.trim())) return "<hr>";
      if (line.startsWith("### ")) return `<h3>${line.slice(4)}</h3>`;
      if (line.startsWith("## ")) return `<h2>${line.slice(3)}</h2>`;
      if (line.trimStart().startsWith("- ") || line.trimStart().startsWith("* "))
        return `<li>${line.trimStart().slice(2)}</li>`;
      return `<p>${line}</p>`;
    })
    .join("\n")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

// ─── Icons ──────────────────────────────────────────────────────────────────

function CopyIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="h-3.5 w-3.5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  );
}

function PdfIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
