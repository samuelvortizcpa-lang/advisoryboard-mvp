"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  ClientAssignment,
  OrgMember,
  createClientAssignmentsApi,
  createOrganizationsApi,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";

interface Props {
  clientId: string;
}

export default function AssignedTeam({ clientId }: Props) {
  const { getToken } = useAuth();
  const { activeOrg, isAdmin } = useOrg();

  const [assignments, setAssignments] = useState<ClientAssignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [orgMembers, setOrgMembers] = useState<OrgMember[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Show for all org members (not just admins), hide for personal workspaces
  const isOrgUser = !!activeOrg && activeOrg.org_type !== "personal";
  const orgId = activeOrg?.id;

  const loadAssignments = useCallback(async () => {
    if (!isOrgUser || !orgId) return;
    try {
      const api = createClientAssignmentsApi(getToken, orgId);
      const result = await api.list(clientId);
      setAssignments(result);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId, clientId, isOrgUser]);

  const loadOrgMembers = useCallback(async () => {
    if (!orgId) return;
    try {
      const api = createOrganizationsApi(getToken, orgId);
      const members = await api.listMembers(orgId);
      setOrgMembers(members.filter((m) => m.is_active));
    } catch {
      // non-fatal
    }
  }, [getToken, orgId]);

  useEffect(() => {
    loadAssignments();
  }, [loadAssignments]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    if (showDropdown) {
      document.addEventListener("mousedown", handleClick);
      return () => document.removeEventListener("mousedown", handleClick);
    }
  }, [showDropdown]);

  // Don't render for personal workspaces
  if (!isOrgUser || !orgId) {
    return null;
  }

  async function handleOpenDropdown() {
    if (orgMembers.length === 0) {
      await loadOrgMembers();
    }
    setShowDropdown(true);
  }

  async function handleAssign(userId: string) {
    setAssigning(true);
    try {
      const api = createClientAssignmentsApi(getToken, orgId!);
      await api.assign(clientId, userId);
      await loadAssignments();
      setShowDropdown(false);
    } catch {
      // non-fatal
    } finally {
      setAssigning(false);
    }
  }

  async function handleRemove(userId: string) {
    setRemoving(userId);
    try {
      const api = createClientAssignmentsApi(getToken, orgId!);
      await api.remove(clientId, userId);
      setAssignments((prev) => prev.filter((a) => a.user_id !== userId));
    } catch {
      // non-fatal
    } finally {
      setRemoving(null);
      setConfirmRemove(null);
    }
  }

  const assignedUserIds = new Set(assignments.map((a) => a.user_id));
  const unassignedMembers = orgMembers.filter((m) => !assignedUserIds.has(m.user_id));

  // Loading skeleton
  if (loading) {
    return (
      <div className="mx-8 my-3 flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50/50 px-4 py-3">
        <span className="text-xs font-medium text-gray-500">Assigned to</span>
        <div className="flex items-center gap-2">
          {[1, 2].map((i) => (
            <div key={i} className="h-7 w-16 animate-pulse rounded-full bg-gray-200" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-8 my-3 flex items-center gap-3 rounded-lg border border-gray-100 bg-gray-50/50 px-4 py-3">
      <span className="shrink-0 text-xs font-medium text-gray-500">Assigned to</span>
      <div className="flex items-center gap-2 flex-wrap">
        {assignments.length === 0 && !isAdmin && (
          <span className="text-xs text-gray-400 italic">No one assigned</span>
        )}

        {assignments.map((a) => {
          const initials = getInitials(a.user_name);
          const name = a.user_name || a.user_email || a.user_id;
          return (
            <div key={a.user_id} className="group relative flex items-center gap-1.5">
              <div className="flex items-center gap-1.5 rounded-full bg-white border border-gray-200 pl-1 pr-2.5 py-0.5">
                <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[10px] font-medium text-blue-700">
                  {initials}
                </div>
                <span className="text-xs font-medium text-gray-700">{name}</span>
                {/* Remove button (admin only) */}
                {isAdmin && (
                  <>
                    {confirmRemove === a.user_id ? (
                      <button
                        onClick={() => handleRemove(a.user_id)}
                        disabled={removing === a.user_id}
                        className="ml-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white"
                        title="Confirm remove"
                      >
                        {removing === a.user_id ? "…" : "✓"}
                      </button>
                    ) : (
                      <button
                        onClick={() => setConfirmRemove(a.user_id)}
                        className="ml-0.5 hidden h-4 w-4 items-center justify-center rounded-full text-gray-400 hover:bg-gray-200 hover:text-gray-600 group-hover:flex"
                        title={`Remove ${name}`}
                      >
                        <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M3 3l6 6M9 3l-6 6" />
                        </svg>
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}

        {/* + Assign button (admin only) */}
        {isAdmin && (
          <div className="relative" ref={dropdownRef}>
            <button
              onClick={handleOpenDropdown}
              className="flex items-center gap-1 rounded-full border border-dashed border-gray-300 px-2.5 py-1 text-xs text-gray-400 hover:border-gray-400 hover:text-gray-500 transition-colors"
              title="Assign team member"
            >
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
              {assignments.length === 0 && <span>Assign</span>}
            </button>

            {/* Dropdown */}
            {showDropdown && (
              <div className="absolute left-0 top-full z-20 mt-1 w-64 rounded-lg border border-gray-200 bg-white py-1 shadow-lg max-h-60 overflow-y-auto">
                {unassignedMembers.length === 0 ? (
                  <p className="px-3 py-2 text-xs text-gray-400">
                    {orgMembers.length === 0 ? "Loading members…" : "All members assigned"}
                  </p>
                ) : (
                  unassignedMembers.map((m) => {
                    const mName = m.user_name || m.user_email || m.user_id;
                    const mInitials = getInitials(m.user_name);
                    return (
                      <button
                        key={m.user_id}
                        onClick={() => handleAssign(m.user_id)}
                        disabled={assigning}
                        className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-gray-50 disabled:opacity-50"
                      >
                        <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[10px] font-medium text-blue-700">
                          {mInitials}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-gray-900">{mName}</p>
                          {m.user_email && m.user_name && (
                            <p className="truncate text-xs text-gray-400">{m.user_email}</p>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function getInitials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}
