"use client";

import { useState, useRef, useEffect } from "react";

export interface MemberRowProps {
  name: string;
  email?: string;
  role?: string;
  stats?: { clients: number; queries: number };
  clientNames?: string[];
  lastActive?: string;
  avatarColor?: string;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0]?.toUpperCase() ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0]?.toUpperCase() ?? "" : "";
  return first + last || "U";
}

const roleBadge: Record<string, string> = {
  admin: "bg-purple-100 text-purple-700",
  member: "bg-gray-100 text-gray-700",
};

export default function MemberRow({ name, email, role, stats, clientNames, lastActive }: MemberRowProps) {
  const [showPopover, setShowPopover] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showPopover) return;
    function handleClick(e: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setShowPopover(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [showPopover]);

  return (
    <div className="flex items-center gap-3 border-b border-gray-100 py-3 last:border-b-0">
      {/* Avatar */}
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-700">
        {getInitials(name)}
      </div>

      {/* Name + email */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-gray-900">{name}</p>
        {email && <p className="truncate text-xs text-gray-500">{email}</p>}
      </div>

      {/* Role badge */}
      {role && (
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${roleBadge[role.toLowerCase()] ?? roleBadge.member}`}
        >
          {role}
        </span>
      )}

      {/* Stats */}
      {stats && (
        <div className="hidden gap-4 text-xs text-gray-500 sm:flex">
          <div className="relative" ref={popoverRef}>
            <button
              onClick={() => clientNames && clientNames.length > 0 && setShowPopover(!showPopover)}
              className={`${clientNames && clientNames.length > 0 ? "cursor-pointer hover:text-gray-700" : "cursor-default"}`}
            >
              {stats.clients} clients
            </button>
            {showPopover && clientNames && clientNames.length > 0 && (
              <div className="absolute left-1/2 top-full z-20 mt-1 -translate-x-1/2 w-48 rounded-lg border border-gray-200 bg-white py-1.5 shadow-lg">
                <p className="px-3 py-1 text-[11px] font-medium text-gray-400 uppercase tracking-wide">Assigned clients</p>
                {clientNames.map((cn) => (
                  <p key={cn} className="truncate px-3 py-1 text-xs text-gray-700">{cn}</p>
                ))}
              </div>
            )}
          </div>
          <span>{stats.queries} queries</span>
        </div>
      )}

      {/* Last active */}
      {lastActive && (
        <span className="shrink-0 text-xs text-gray-400">{lastActive}</span>
      )}
    </div>
  );
}
