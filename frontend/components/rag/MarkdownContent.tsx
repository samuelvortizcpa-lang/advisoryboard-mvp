"use client";

import { ReactNode } from "react";

/**
 * Lightweight markdown renderer for chat messages.
 * Handles: ## headers, **bold**, - bullets, 1. numbered lists, `code`.
 * No external dependencies required.
 */

function parseInline(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
  // Match **bold**, `code`, or plain text
  const regex = /(\*\*(.+?)\*\*)|(`(.+?)`)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // Text before this match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    if (match[2]) {
      // **bold**
      parts.push(
        <strong key={match.index} className="font-semibold">
          {match[2]}
        </strong>
      );
    } else if (match[4]) {
      // `code`
      parts.push(
        <code
          key={match.index}
          className="rounded bg-gray-200 px-1 py-0.5 text-xs font-mono"
        >
          {match[4]}
        </code>
      );
    }
    lastIndex = regex.lastIndex;
  }

  // Remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}

interface Props {
  content: string;
}

export default function MarkdownContent({ content }: Props) {
  const lines = content.split("\n");
  const elements: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // ### H3
    if (line.startsWith("### ")) {
      elements.push(
        <h4 key={i} className="mt-3 mb-1 text-sm font-bold text-gray-900">
          {parseInline(line.slice(4))}
        </h4>
      );
      i++;
      continue;
    }

    // ## H2
    if (line.startsWith("## ")) {
      elements.push(
        <h3 key={i} className="mt-4 mb-1.5 text-sm font-bold text-gray-900 border-b border-gray-200 pb-1">
          {parseInline(line.slice(3))}
        </h3>
      );
      i++;
      continue;
    }

    // Bullet list: - item
    if (/^[-•] /.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^[-•] /.test(lines[i])) {
        items.push(
          <li key={i} className="ml-4 list-disc text-sm leading-relaxed">
            {parseInline(lines[i].replace(/^[-•] /, ""))}
          </li>
        );
        i++;
      }
      elements.push(
        <ul key={`ul-${i}`} className="my-1 space-y-0.5">
          {items}
        </ul>
      );
      continue;
    }

    // Numbered list: 1. item
    if (/^\d+\.\s/.test(line)) {
      const items: ReactNode[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(
          <li key={i} className="ml-4 list-decimal text-sm leading-relaxed">
            {parseInline(lines[i].replace(/^\d+\.\s/, ""))}
          </li>
        );
        i++;
      }
      elements.push(
        <ol key={`ol-${i}`} className="my-1 space-y-0.5">
          {items}
        </ol>
      );
      continue;
    }

    // Empty line = spacing
    if (line.trim() === "") {
      elements.push(<div key={i} className="h-2" />);
      i++;
      continue;
    }

    // Regular paragraph
    elements.push(
      <p key={i} className="text-sm leading-relaxed">
        {parseInline(line)}
      </p>
    );
    i++;
  }

  return <div className="space-y-0.5">{elements}</div>;
}
