"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState, useCallback } from "react";

import {
  createOrganizationsApi,
  createStripeApi,
  createClientAssignmentsApi,
  OrgDetail,
  OrgMember,
  SeatInfo,
  MemberAssignments,
} from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import Link from "next/link";

// ─── Helpers ────────────────────────────────────────────────────────────────

const ROLE_BADGE: Record<string, string> = {
  admin: "bg-purple-100 text-purple-700",
  member: "bg-blue-100 text-blue-700",
  readonly: "bg-gray-100 text-gray-600",
};

function fmtDate(iso: string | null) {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function OrganizationSettingsPage() {
  const { getToken } = useAuth();
  const { orgs, activeOrg, setActiveOrg, isLoading: orgLoading } = useOrg();

  // Data state
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [orgDetail, setOrgDetail] = useState<OrgDetail | null>(null);
  const [members, setMembers] = useState<OrgMember[]>([]);

  // Edit state
  const [editName, setEditName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [savingName, setSavingName] = useState(false);

  // Invite modal state
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviting, setInviting] = useState(false);

  // Inline feedback
  const [feedback, setFeedback] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  // Action loading
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Role dropdown
  const [roleDropdown, setRoleDropdown] = useState<string | null>(null);

  // Remove confirmation
  const [removeConfirm, setRemoveConfirm] = useState<string | null>(null);

  // Assignment overview state
  const [assignmentData, setAssignmentData] = useState<MemberAssignments[]>([]);
  const [assignmentsLoading, setAssignmentsLoading] = useState(false);

  // Seat management state
  const [seatInfo, setSeatInfo] = useState<SeatInfo | null>(null);
  const [showManageSeats, setShowManageSeats] = useState(false);
  const [newAddonSeats, setNewAddonSeats] = useState(0);
  const [updatingSeats, setUpdatingSeats] = useState(false);

  const showFeedback = (message: string, type: "success" | "error") => {
    setFeedback({ message, type });
    setTimeout(() => setFeedback(null), 3000);
  };

  const api = useCallback(() => createOrganizationsApi(getToken), [getToken]);

  const loadAssignments = useCallback(async (orgId: string) => {
    setAssignmentsLoading(true);
    try {
      const assignApi = createClientAssignmentsApi(getToken, orgId);
      const result = await assignApi.listOrgAssignments(orgId);
      setAssignmentData(result);
    } catch {
      // non-fatal
    } finally {
      setAssignmentsLoading(false);
    }
  }, [getToken]);

  // Sync selectedOrgId from context
  useEffect(() => {
    if (orgLoading) return;
    if (activeOrg && !selectedOrgId) {
      setSelectedOrgId(activeOrg.id);
    }
    setLoading(false);
  }, [orgLoading, activeOrg, selectedOrgId]);

  // Load org detail + members
  const stripeApi = useCallback(() => createStripeApi(getToken), [getToken]);

  const loadOrgDetail = useCallback(async () => {
    if (!selectedOrgId) return;
    try {
      const [detail, memberList] = await Promise.all([
        api().get(selectedOrgId),
        api().listMembers(selectedOrgId),
      ]);
      setOrgDetail(detail);
      setMembers(memberList);
      setNameValue(detail.name);

      // Load assignment overview
      loadAssignments(selectedOrgId);

      // Load seat info for firm tier
      if (detail.subscription_tier === "firm") {
        try {
          const seats = await stripeApi().getSeats();
          setSeatInfo(seats);
        } catch {
          // Seat info not available — non-critical
        }
      } else {
        setSeatInfo(null);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load organization details"
      );
    }
  }, [api, stripeApi, selectedOrgId, loadAssignments]);

  useEffect(() => {
    if (selectedOrgId) loadOrgDetail();
  }, [selectedOrgId, loadOrgDetail]);

  // ── Actions ─────────────────────────────────────────────────────────────

  async function handleSaveName() {
    if (!selectedOrgId || !nameValue.trim()) return;
    setSavingName(true);
    try {
      const updated = await api().update(selectedOrgId, {
        name: nameValue.trim(),
      });
      setOrgDetail(updated);
      setEditName(false);
      showFeedback("Organization name updated", "success");
    } catch (err) {
      showFeedback(
        err instanceof Error ? err.message : "Failed to update name",
        "error"
      );
    } finally {
      setSavingName(false);
    }
  }

  async function handleInvite() {
    if (!selectedOrgId || !inviteEmail.trim()) return;
    setInviting(true);
    try {
      await api().inviteMember(selectedOrgId, inviteEmail.trim(), inviteRole);
      setShowInvite(false);
      setInviteEmail("");
      setInviteRole("member");
      showFeedback("Member added successfully", "success");
      await loadOrgDetail();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to add member";
      if (msg.includes("Seat limit") || msg.includes("seat limit")) {
        showFeedback(
          "Seat limit reached. Add more seats in Organization Settings to invite more members.",
          "error"
        );
      } else {
        showFeedback(msg, "error");
      }
    } finally {
      setInviting(false);
    }
  }

  async function handleUpdateSeats() {
    setUpdatingSeats(true);
    try {
      const updated = await stripeApi().updateSeats(newAddonSeats);
      setSeatInfo(updated);
      setShowManageSeats(false);
      showFeedback("Seats updated successfully", "success");
      await loadOrgDetail();
    } catch (err) {
      showFeedback(
        err instanceof Error ? err.message : "Failed to update seats",
        "error"
      );
    } finally {
      setUpdatingSeats(false);
    }
  }

  async function handleRoleChange(userId: string, newRole: string) {
    if (!selectedOrgId) return;
    setActionLoading(userId);
    setRoleDropdown(null);
    try {
      await api().updateMemberRole(selectedOrgId, userId, newRole);
      showFeedback("Role updated", "success");
      await loadOrgDetail();
    } catch (err) {
      showFeedback(
        err instanceof Error ? err.message : "Failed to update role",
        "error"
      );
    } finally {
      setActionLoading(null);
    }
  }

  async function handleRemoveMember(userId: string) {
    if (!selectedOrgId) return;
    setActionLoading(userId);
    setRemoveConfirm(null);
    try {
      await api().removeMember(selectedOrgId, userId);
      showFeedback("Member removed", "success");
      await loadOrgDetail();
    } catch (err) {
      showFeedback(
        err instanceof Error ? err.message : "Failed to remove member",
        "error"
      );
    } finally {
      setActionLoading(null);
    }
  }

  // ── Loading ─────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6 animate-pulse">
        <div className="mx-auto max-w-4xl space-y-6">
          <div className="h-8 w-56 rounded bg-gray-200" />
          <div className="h-4 w-72 rounded bg-gray-200" />
          <div className="h-40 rounded-xl bg-white border border-gray-200 shadow-sm" />
          <div className="h-64 rounded-xl bg-white border border-gray-200 shadow-sm" />
        </div>
      </div>
    );
  }

  if (error && orgs.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="mx-auto max-w-4xl">
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-600">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="mt-3 text-sm font-medium text-red-700 hover:underline"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (orgs.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Organization</h1>
            <p className="mt-1 text-sm text-gray-500">
              Manage your firm&apos;s team and settings
            </p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-10 text-center shadow-sm">
            <p className="text-sm text-gray-500">
              You&apos;re not part of any organization yet. Upgrade to
              Professional or Firm tier to create one.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const isAdmin = orgDetail?.role === "admin";
  const tierLabel = orgDetail?.subscription_tier ?? "free";

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* ── Header ──────────────────────────────────────────────────── */}
        <div>
          <h1 className="text-xl font-bold text-gray-900">Organization</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your firm&apos;s team and settings
          </p>
        </div>

        {/* Org selector (if user has multiple orgs) */}
        {orgs.length > 1 && (
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">
              Organization:
            </label>
            <select
              value={selectedOrgId ?? ""}
              onChange={(e) => setSelectedOrgId(e.target.value)}
              className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 shadow-sm"
            >
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* ── Inline feedback ─────────────────────────────────────────── */}
        {feedback && (
          <div
            className={`rounded-xl border px-5 py-3 text-sm font-medium ${
              feedback.type === "success"
                ? "border-green-200 bg-green-50 text-green-700"
                : "border-red-200 bg-red-50 text-red-700"
            }`}
          >
            {feedback.message}
          </div>
        )}

        {/* ── Section 1: Org Info ──────────────────────────────────────── */}
        {orgDetail && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">
              Organization Info
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {/* Name */}
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Name
                </label>
                {editName ? (
                  <div className="mt-1 flex items-center gap-2">
                    <input
                      type="text"
                      value={nameValue}
                      onChange={(e) => setNameValue(e.target.value)}
                      className="flex-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleSaveName}
                      disabled={savingName}
                      className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {savingName ? "Saving..." : "Save"}
                    </button>
                    <button
                      onClick={() => {
                        setEditName(false);
                        setNameValue(orgDetail.name);
                      }}
                      className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="mt-1 flex items-center gap-2">
                    <p className="text-sm text-gray-900">{orgDetail.name}</p>
                    {isAdmin && (
                      <button
                        onClick={() => setEditName(true)}
                        className="text-xs text-blue-600 hover:text-blue-700"
                      >
                        Edit
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* Slug */}
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Slug
                </label>
                <p className="mt-1 text-sm text-gray-900">{orgDetail.slug}</p>
              </div>

              {/* Type */}
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Type
                </label>
                <p className="mt-1 text-sm capitalize text-gray-900">
                  {orgDetail.org_type}
                </p>
              </div>

              {/* Created */}
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Created
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {fmtDate(orgDetail.created_at)}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* ── Section 2: Team Members ──────────────────────────────────── */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">
                Team Members
              </h2>
              {orgDetail && (
                <p className="mt-0.5 text-xs text-gray-500">
                  {orgDetail.member_count} of {orgDetail.max_members} seats used
                </p>
              )}
            </div>
            {isAdmin && (
              <button
                onClick={() => setShowInvite(true)}
                className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white hover:bg-blue-700"
              >
                Add Member
              </button>
            )}
          </div>

          {/* Invite modal (inline) */}
          {showInvite && (
            <div className="border-b border-gray-100 bg-gray-50 px-5 py-4">
              <p className="text-sm font-medium text-gray-900 mb-3">
                Add a team member
              </p>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                <div className="flex-1">
                  <label className="text-xs font-medium text-gray-500">
                    Email address
                  </label>
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder="colleague@firm.com"
                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  />
                </div>
                <div className="w-36">
                  <label className="text-xs font-medium text-gray-500">
                    Role
                  </label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700"
                  >
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                    <option value="readonly">Read-only</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleInvite}
                    disabled={inviting || !inviteEmail.trim()}
                    className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {inviting ? "Adding..." : "Add"}
                  </button>
                  <button
                    onClick={() => {
                      setShowInvite(false);
                      setInviteEmail("");
                      setInviteRole("member");
                    }}
                    className="rounded-lg border border-gray-200 px-4 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Members table */}
          {members.length === 0 ? (
            <div className="p-10 text-center">
              <p className="text-sm text-gray-400">No members found.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-gray-400">
                    <th className="px-5 py-3">Member</th>
                    <th className="px-5 py-3">Role</th>
                    <th className="px-5 py-3">Joined</th>
                    {isAdmin && <th className="px-5 py-3">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {members.map((m) => {
                    const displayName = m.user_name || m.user_email || m.user_id;
                    const isActioning = actionLoading === m.user_id;

                    return (
                      <tr key={m.id} className="border-b border-gray-50">
                        <td className="px-5 py-3">
                          <p className="font-medium text-gray-900">
                            {displayName}
                          </p>
                          {m.user_email && m.user_name && (
                            <p className="text-xs text-gray-400">
                              {m.user_email}
                            </p>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          <span
                            className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${
                              ROLE_BADGE[m.role] ?? "bg-gray-100 text-gray-600"
                            }`}
                          >
                            {m.role}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-xs text-gray-500">
                          {fmtDate(m.joined_at)}
                        </td>
                        {isAdmin && (
                          <td className="px-5 py-3">
                            <div className="flex flex-col gap-2">
                              <div className="flex items-center gap-2">
                                {/* Change Role */}
                                <div className="relative">
                                  <button
                                    onClick={() =>
                                      setRoleDropdown(
                                        roleDropdown === m.user_id
                                          ? null
                                          : m.user_id
                                      )
                                    }
                                    disabled={isActioning}
                                    className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                                  >
                                    Change Role
                                  </button>
                                  {roleDropdown === m.user_id && (
                                    <div className="absolute right-0 top-full z-10 mt-1 w-36 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                                      {(
                                        ["admin", "member", "readonly"] as const
                                      ).map((r) => (
                                        <button
                                          key={r}
                                          onClick={() =>
                                            handleRoleChange(m.user_id, r)
                                          }
                                          className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs hover:bg-gray-50 ${
                                            m.role === r
                                              ? "font-semibold text-blue-600"
                                              : "text-gray-700"
                                          }`}
                                        >
                                          <span className="capitalize">{r}</span>
                                          {m.role === r && (
                                            <span className="ml-auto text-blue-600">
                                              &#10003;
                                            </span>
                                          )}
                                        </button>
                                      ))}
                                    </div>
                                  )}
                                </div>

                                {/* Remove */}
                                <button
                                  onClick={() =>
                                    setRemoveConfirm(
                                      removeConfirm === m.user_id
                                        ? null
                                        : m.user_id
                                    )
                                  }
                                  disabled={isActioning}
                                  className="rounded-md border border-red-200 px-2.5 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                                >
                                  Remove
                                </button>

                                {isActioning && (
                                  <svg
                                    className="h-4 w-4 animate-spin text-gray-400"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                  >
                                    <circle
                                      className="opacity-25"
                                      cx="12"
                                      cy="12"
                                      r="10"
                                      stroke="currentColor"
                                      strokeWidth="4"
                                    />
                                    <path
                                      className="opacity-75"
                                      fill="currentColor"
                                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                                    />
                                  </svg>
                                )}
                              </div>

                              {/* Remove confirmation */}
                              {removeConfirm === m.user_id && (
                                <div className="rounded-md border border-red-200 bg-red-50 p-2.5">
                                  <p className="text-xs text-red-800">
                                    Remove{" "}
                                    <span className="font-medium">
                                      {displayName}
                                    </span>{" "}
                                    from the organization?
                                  </p>
                                  <div className="mt-2 flex gap-2">
                                    <button
                                      onClick={() =>
                                        handleRemoveMember(m.user_id)
                                      }
                                      className="rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700"
                                    >
                                      Confirm
                                    </button>
                                    <button
                                      onClick={() => setRemoveConfirm(null)}
                                      className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
                                    >
                                      Cancel
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Section 3: Client Assignments ────────────────────────── */}
        {isAdmin && members.length > 0 && (
          <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-100 px-5 py-4">
              <h2 className="text-sm font-semibold text-gray-900">Client Assignments</h2>
              <p className="mt-0.5 text-xs text-gray-500">
                See which clients are assigned to each team member
              </p>
            </div>
            {assignmentsLoading ? (
              <div className="p-10 text-center">
                <p className="text-sm text-gray-400 animate-pulse">Loading assignments…</p>
              </div>
            ) : assignmentData.length === 0 ? (
              <div className="p-10 text-center">
                <p className="text-sm text-gray-500">
                  No client assignments yet. Assign team members to clients from each client&apos;s detail page.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-gray-400">
                      <th className="px-5 py-3">Member</th>
                      <th className="px-5 py-3">Assigned Clients</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assignmentData.map((ma) => (
                      <tr key={ma.user_id} className="border-b border-gray-50">
                        <td className="px-5 py-3">
                          <p className="font-medium text-gray-900">{ma.user_name || ma.user_id}</p>
                          {ma.user_email && (
                            <p className="text-xs text-gray-400">{ma.user_email}</p>
                          )}
                        </td>
                        <td className="px-5 py-3">
                          {ma.assigned_clients.length === 0 ? (
                            <span className="text-xs text-gray-400">None</span>
                          ) : (
                            <div className="flex flex-wrap gap-1.5">
                              {ma.assigned_clients.map((c) => (
                                <Link
                                  key={c.client_id}
                                  href={`/dashboard/clients/${c.client_id}`}
                                  className="inline-block rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-200 transition-colors"
                                >
                                  {c.client_name}
                                </Link>
                              ))}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── Section 4: Seats & Billing (Firm only) ─────────────────── */}
        {orgDetail && tierLabel === "firm" && seatInfo && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-gray-900">Seats & Billing</h2>
              {isAdmin && (
                <button
                  onClick={() => {
                    setNewAddonSeats(seatInfo.addon_purchased);
                    setShowManageSeats(true);
                  }}
                  className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50"
                >
                  Manage Seats
                </button>
              )}
            </div>
            {/* Seat progress bar */}
            <div className="mb-3">
              <div className="flex items-baseline justify-between mb-1">
                <p className="text-xs font-medium text-gray-700">Seats Used</p>
                <p className="text-xs text-gray-500">
                  {seatInfo.current_used} of {seatInfo.total_allowed}
                </p>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                {(() => {
                  const pct = seatInfo.total_allowed > 0
                    ? Math.min(100, (seatInfo.current_used / seatInfo.total_allowed) * 100)
                    : 0;
                  const color = pct > 90 ? "bg-red-500" : pct > 70 ? "bg-yellow-400" : "bg-green-500";
                  return (
                    <div
                      className={`h-full rounded-full transition-all ${color}`}
                      style={{ width: `${Math.max(2, pct)}%` }}
                    />
                  );
                })()}
              </div>
            </div>
            <p className="text-xs text-gray-500">
              {seatInfo.included} included + {seatInfo.addon_purchased} add-on = {seatInfo.total_allowed} total
            </p>
          </div>
        )}

        {orgDetail && tierLabel !== "firm" && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900 mb-2">Seats & Billing</h2>
            <p className="text-xs text-gray-500">
              <Link href="/dashboard/settings/subscriptions" className="text-blue-600 hover:text-blue-700 font-medium">
                Upgrade to Firm
              </Link>{" "}
              to add team members and manage seats.
            </p>
          </div>
        )}

        {/* Manage Seats modal */}
        {showManageSeats && seatInfo && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-xl">
              <h3 className="text-sm font-semibold text-gray-900">Manage Add-On Seats</h3>
              <p className="mt-1 text-xs text-gray-500">
                Your Firm plan includes 3 seats. Add-on seats are ${seatInfo.per_seat_price}/mo each.
              </p>
              <div className="mt-4">
                <label className="text-xs font-medium text-gray-500">
                  Current add-on seats: {seatInfo.addon_purchased}
                </label>
              </div>
              <div className="mt-2">
                <label className="text-xs font-medium text-gray-500">
                  New add-on seats
                </label>
                <input
                  type="number"
                  min={0}
                  max={47}
                  value={newAddonSeats}
                  onChange={(e) => setNewAddonSeats(Math.max(0, Math.min(47, parseInt(e.target.value) || 0)))}
                  className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              <div className="mt-3 rounded-lg bg-gray-50 p-3">
                <p className="text-xs text-gray-600">
                  From ${(349 + seatInfo.addon_purchased * seatInfo.per_seat_price).toLocaleString()}/mo
                  {" → "}
                  <span className="font-semibold text-gray-900">
                    ${(349 + newAddonSeats * seatInfo.per_seat_price).toLocaleString()}/mo
                  </span>
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  Changes will be prorated to your current billing cycle
                </p>
              </div>
              <div className="mt-4 flex gap-2">
                <button
                  onClick={handleUpdateSeats}
                  disabled={updatingSeats || newAddonSeats === seatInfo.addon_purchased}
                  className="flex-1 rounded-lg bg-blue-600 px-4 py-2 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {updatingSeats ? "Updating\u2026" : "Update Seats"}
                </button>
                <button
                  onClick={() => setShowManageSeats(false)}
                  className="rounded-lg border border-gray-200 px-4 py-2 text-xs font-medium text-gray-600 hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Section 4: Subscription ──────────────────────────────────── */}
        {orgDetail && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">
              Subscription
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Current Plan
                </label>
                <p className="mt-1">
                  <span
                    className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${
                      tierLabel === "free"
                        ? "bg-emerald-100 text-emerald-700"
                        : tierLabel === "starter"
                        ? "bg-gray-100 text-gray-700"
                        : tierLabel === "professional"
                        ? "bg-blue-100 text-blue-700"
                        : tierLabel === "firm"
                        ? "bg-purple-100 text-purple-700"
                        : "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {tierLabel}
                  </span>
                </p>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Team Seats
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {orgDetail.member_count} / {orgDetail.max_members}
                </p>
              </div>
              <div>
                <label className="text-xs font-medium text-gray-500">
                  Clients
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {orgDetail.client_count}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
