"use client";

import type { CadenceTemplateSummary } from "@/lib/api";
import TemplateRow from "./TemplateRow";

interface TemplateListSectionProps {
  title: string;
  templates: CadenceTemplateSummary[];
  basePath: string;
  emptyMessage?: string;
}

export default function TemplateListSection({
  title,
  templates,
  basePath,
  emptyMessage,
}: TemplateListSectionProps) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
        {title}
      </h3>
      {templates.length > 0 ? (
        <div className="space-y-2">
          {templates.map((t) => (
            <TemplateRow
              key={t.id}
              template={t}
              href={`${basePath}/${t.id}`}
            />
          ))}
        </div>
      ) : emptyMessage ? (
        <p className="rounded-lg border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-400">
          {emptyMessage}
        </p>
      ) : null}
    </div>
  );
}
