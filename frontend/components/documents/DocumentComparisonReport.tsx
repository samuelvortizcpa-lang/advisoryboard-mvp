"use client";

import { CompareDocumentMeta, ComparisonType } from "@/lib/api";

interface Props {
  comparisonType: ComparisonType;
  documents: CompareDocumentMeta[];
  report: string;
  onClose: () => void;
}

const TYPE_LABELS: Record<ComparisonType, string> = {
  summary: "Summary Comparison",
  changes: "Change Analysis",
  financial: "Financial Comparison",
};

export default function DocumentComparisonReport({
  comparisonType,
  documents,
  report,
  onClose,
}: Props) {
  return (
    <div className="mt-6 overflow-hidden rounded-xl border border-blue-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-blue-100 bg-blue-50 px-5 py-3">
        <div>
          <h3 className="text-sm font-semibold text-blue-900">
            {TYPE_LABELS[comparisonType]}
          </h3>
          <p className="mt-0.5 text-xs text-blue-600">
            Comparing{" "}
            {documents.map((d, i) => (
              <span key={d.id}>
                <span className="font-medium">{d.filename}</span>
                {i < documents.length - 1 && " · "}
              </span>
            ))}
          </p>
        </div>
        <button
          onClick={onClose}
          title="Dismiss report"
          className="rounded-lg p-1.5 text-blue-400 transition-colors hover:bg-blue-100 hover:text-blue-700"
        >
          <CloseIcon />
        </button>
      </div>

      {/* Report body */}
      <div className="prose-sm px-5 py-5 text-gray-700">
        <MarkdownRenderer content={report} />
      </div>
    </div>
  );
}

// ─── Lightweight Markdown renderer ────────────────────────────────────────────
// Handles: ## headings, **bold**, bullet lists (- item), horizontal rules (---),
// and plain paragraphs. No external dependencies required.

function MarkdownRenderer({ content }: { content: string }) {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Blank line
    if (line.trim() === "") {
      i++;
      continue;
    }

    // Horizontal rule
    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={i} className="my-4 border-gray-200" />);
      i++;
      continue;
    }

    // ## Heading (H2)
    if (line.startsWith("## ")) {
      elements.push(
        <h2 key={i} className="mt-5 mb-2 text-sm font-semibold text-gray-900 first:mt-0">
          {line.slice(3)}
        </h2>
      );
      i++;
      continue;
    }

    // ### Heading (H3)
    if (line.startsWith("### ")) {
      elements.push(
        <h3 key={i} className="mt-4 mb-1.5 text-sm font-semibold text-gray-800 first:mt-0">
          {line.slice(4)}
        </h3>
      );
      i++;
      continue;
    }

    // Bullet list — collect consecutive bullet lines
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

    // Table row (| ... |)
    if (line.trimStart().startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trimStart().startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      elements.push(<MarkdownTable key={`tbl-${i}`} lines={tableLines} />);
      continue;
    }

    // Paragraph — collect consecutive non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("## ") &&
      !lines[i].startsWith("### ") &&
      !/^---+$/.test(lines[i].trim()) &&
      !lines[i].trimStart().startsWith("- ") &&
      !lines[i].trimStart().startsWith("* ") &&
      !lines[i].trimStart().startsWith("|")
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

// Render inline markdown: **bold** and *italic*
function InlineMarkdown({ text }: { text: string }) {
  // Split on **bold** and *italic* tokens
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

// Render a simple markdown table
function MarkdownTable({ lines }: { lines: string[] }) {
  const rows = lines
    .filter((l) => !/^\|[-| ]+\|$/.test(l.trim())) // skip separator rows
    .map((l) =>
      l
        .split("|")
        .slice(1, -1)
        .map((cell) => cell.trim())
    );

  if (rows.length === 0) return null;

  const [header, ...body] = rows;

  return (
    <div className="my-3 overflow-x-auto">
      <table className="min-w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-50">
            {header.map((cell, i) => (
              <th
                key={i}
                className="border border-gray-200 px-3 py-1.5 text-left font-semibold text-gray-700"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, ri) => (
            <tr key={ri} className={ri % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className="border border-gray-200 px-3 py-1.5 text-gray-700"
                >
                  <InlineMarkdown text={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CloseIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
