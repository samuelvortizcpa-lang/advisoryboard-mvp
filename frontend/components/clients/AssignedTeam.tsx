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

  // Derived: should this component be visible?
  const isVisible =
    !!activeOrg && activeOrg.org_type !== "personal" && isAdmin;
  const orgId = activeOrg?.id;

  const loadAssignments = useCallback(async () => {
    if (!isVisible || !orgId) return;
    try {
      const api = createClientAssignmentsApi(getToken, orgId);
      const result = await api.list(clientId);
      setAssignments(result);
    } catch {
      // non-fatal
    } finally {
      setLoading(false);
    }
  }, [getToken, orgId, clientId, isVisible]);

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

  // Only render for org admins in non-personal orgs
  if (!isVisible || !orgId) {
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
      <div className="px-8 py-3">
        <p className="text-sm font-semibold text-gray-900 mb-2">Assigned team</p>
        <div className="flex items-center gap-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-7 w-7 animate-pulse rounded-full bg-gray-200" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="px-8 py-3 border-b border-gray-100">
      <p className="text-sm font-semibold text-gray-900 mb-2">Assigned team</p>
      <div className="flex items-center gap-2 flex-wrap">
        {assignments.map((a) => {
          const initials = getInitials(a.user_name);
          return (
            <div key={a.user_id} className="group relative">
              <div
                className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-[11px] font-medium text-blue-700 cursor-default"
                title={a.user_name || a.user_email || a.user_id}
              >
                {initials}
              </div>
              {/* Remove button on hover */}
              {confirmRemove === a.user_id ? (
                <button
                  onClick={() => handleRemove(a.user_id)}
                  disabled={removing === a.user_id}
                  className="absolute -top-1 -right-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-red-600 text-[8px] font-bold text-white shadow-sm"
                  title="Confirm remove"
                >
                  {removing === a.user_id ? "..." : "!"}
                </button>
              ) : (
                <button
                  onClick={() => setConfirmRemove(a.user_id)}
                  className="absolute -top-1 -right-1 hidden h-3.5 w-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-bold text-white shadow-sm group-hover:flex"
                  title={`Remove ${a.user_name || a.user_id}`}
                >
                  x
                </button>
              )}
            </div>
          );
        })}

        {/* + Assign button */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={handleOpenDropdown}
            className="flex h-7 w-7 items-center justify-center rounded-full border border-dashed border-gray-300 text-gray-400 hover:border-gray-400 hover:text-gray-500 transition-colors"
            title="Assign team member"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </button>
          {assignments.length === 0 && (
            <span className="ml-1 text-xs text-gray-400">Assign team members</span>
          )}

          {/* Dropdown */}
          {showDropdown && (
            <div className="absolute left-0 top-full z-20 mt-1 w-64 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
              {unassignedMembers.length === 0 ? (
                <p className="px-3 py-2 text-xs text-gray-400">
                  {orgMembers.length === 0 ? "Loading members..." : "All members assigned"}
                </p>
              ) : (
                unassignedMembers.map((m) => {
                  const name = m.user_name || m.user_email || m.user_id;
                  const initials = getInitials(m.user_name);
                  return (
                    <button
                      key={m.user_id}
                      onClick={() => handleAssign(m.user_id)}
                      disabled={assigning}
                      className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-gray-50 disabled:opacity-50"
                    >
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[10px] font-medium text-blue-700">
                        {initials}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm text-gray-900">{name}</p>
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
