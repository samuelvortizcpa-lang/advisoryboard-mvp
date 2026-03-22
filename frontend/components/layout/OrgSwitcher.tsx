"use client";

import { useState, useRef, useEffect } from "react";
import { useOrg } from "@/contexts/OrgContext";

export default function OrgSwitcher() {
  const { orgs, activeOrg, setActiveOrg } = useOrg();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  // Don't render for single-org users
  if (orgs.length <= 1) return null;

  return (
    <div ref={ref} className="relative px-3 pb-2">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-2.5 py-2 text-left transition-colors hover:bg-gray-100"
      >
        <SwitchBuildingIcon />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-gray-700">
          {activeOrg?.name ?? "Select org"}
        </span>
        <ChevronIcon />
      </button>

      {open && (
        <div className="absolute bottom-full left-3 right-3 z-30 mb-1 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
          {orgs.map((o) => {
            const isActive = o.id === activeOrg?.id;
            return (
              <button
                key={o.id}
                onClick={() => {
                  setActiveOrg(o);
                  setOpen(false);
                }}
                className={`flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-gray-50 ${
                  isActive ? "font-semibold text-blue-600" : "text-gray-700"
                }`}
              >
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    o.org_type === "firm" ? "bg-purple-400" : "bg-gray-300"
                  }`}
                />
                <span className="min-w-0 flex-1 truncate">{o.name}</span>
                {isActive && (
                  <span className="ml-auto text-blue-600">&#10003;</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SwitchBuildingIcon() {
  return (
    <svg
      className="h-3.5 w-3.5 shrink-0 text-gray-400"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21"
      />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg
      className="h-3 w-3 shrink-0 text-gray-400"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
        clipRule="evenodd"
      />
    </svg>
  );
}
