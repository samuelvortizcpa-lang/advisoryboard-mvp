"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState, useCallback } from "react";

import {
  createAdminApi,
  AdminSubscription,
  AdminSubscriptionSummary,
} from "@/lib/api";

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtDate(iso: string | null) {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

const TIER_BADGE: Record<string, string> = {
  starter: "bg-gray-100 text-gray-700",
  professional: "bg-blue-100 text-blue-700",
  firm: "bg-purple-100 text-purple-700",
};

const TIERS = ["starter", "professional", "firm"] as const;

function progressColor(pct: number) {
  if (pct > 95) return "bg-red-500";
  if (pct > 80) return "bg-orange-400";
  if (pct > 60) return "bg-yellow-400";
  return "bg-green-500";
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function SubscriptionManagementPage() {
  const { getToken } = useAuth();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subs, setSubs] = useState<AdminSubscription[]>([]);
  const [summary, setSummary] = useState<AdminSubscriptionSummary | null>(null);

  // Inline interaction state
  const [tierDropdown, setTierDropdown] = useState<string | null>(null); // user_id or null
  const [resetConfirm, setResetConfirm] = useState<string | null>(null); // user_id or null
  const [actionLoading, setActionLoading] = useState<string | null>(null); // user_id or null
  const [feedback, setFeedback] = useState<{ userId: string; message: string; type: "success" | "error" } | null>(null);

  const showFeedback = (userId: string, message: string, type: "success" | "error") => {
    setFeedback({ userId, message, type });
    setTimeout(() => setFeedback((f) => (f?.userId === userId ? null : f)), 3000);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const api = createAdminApi(getToken);
      const [s, sum] = await Promise.all([
        api.listSubscriptions(),
        api.subscriptionSummary(),
      ]);
      setSubs(s);
      setSummary(sum);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load subscriptions");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => { loadData(); }, [loadData]);

  async function handleTierChange(userId: string, tier: string) {
    setActionLoading(userId);
    setTierDropdown(null);
    try {
      await createAdminApi(getToken).updateTier(userId, tier);
      showFeedback(userId, `Tier updated to ${tier}`, "success");
      await loadData();
    } catch (err) {
      showFeedback(userId, err instanceof Error ? err.message : "Failed to update tier", "error");
    } finally {
      setActionLoading(null);
    }
  }

  async function handleResetUsage(userId: string) {
    setActionLoading(userId);
    setResetConfirm(null);
    try {
      await createAdminApi(getToken).resetUsage(userId);
      showFeedback(userId, "Usage reset successfully", "success");
      await loadData();
    } catch (err) {
      showFeedback(userId, err instanceof Error ? err.message : "Failed to reset usage", "error");
    } finally {
      setActionLoading(null);
    }
  }

  // ── Loading ─────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6 animate-pulse">
        <div className="mx-auto max-w-5xl space-y-6">
          <div className="h-8 w-56 rounded bg-gray-200" />
          <div className="h-4 w-72 rounded bg-gray-200" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-white border border-gray-200 shadow-sm" />
            ))}
          </div>
          <div className="h-64 rounded-xl bg-white border border-gray-200 shadow-sm" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="mx-auto max-w-5xl">
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p className="text-sm text-red-600">{error}</p>
            <button onClick={loadData} className="mt-3 text-sm font-medium text-red-700 hover:underline">
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-5xl space-y-6">

        {/* ── Header ────────────────────────────────────────────────────── */}
        <div>
          <h1 className="text-xl font-bold text-gray-900">Subscription Management</h1>
          <p className="mt-1 text-sm text-gray-500">Manage user tiers and quota usage</p>
        </div>

        {/* ── Summary Cards ─────────────────────────────────────────────── */}
        {summary && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard label="Total Users" value={summary.total_users} />
            <SummaryCard
              label="Starter"
              value={summary.by_tier.starter ?? 0}
              badgeClass="bg-gray-100 text-gray-700"
            />
            <SummaryCard
              label="Professional"
              value={summary.by_tier.professional ?? 0}
              badgeClass="bg-blue-100 text-blue-700"
            />
            <SummaryCard
              label="Firm"
              value={summary.by_tier.firm ?? 0}
              badgeClass="bg-purple-100 text-purple-700"
            />
          </div>
        )}

        {/* Near/over limit badges */}
        {summary && (summary.users_near_limit > 0 || summary.users_over_limit > 0) && (
          <div className="flex items-center gap-3">
            {summary.users_near_limit > 0 && (
              <span className="inline-flex items-center rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800">
                {summary.users_near_limit} near limit
              </span>
            )}
            {summary.users_over_limit > 0 && (
              <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
                {summary.users_over_limit} over limit
              </span>
            )}
          </div>
        )}

        {/* ── Table ─────────────────────────────────────────────────────── */}
        <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
          {subs.length === 0 ? (
            <div className="p-10 text-center">
              <p className="text-sm text-gray-400">No subscriptions found. Users will appear here after their first sign-in.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs font-medium uppercase tracking-wide text-gray-400">
                    <th className="px-5 py-3">User</th>
                    <th className="px-5 py-3">Tier</th>
                    <th className="px-5 py-3">Strategic Queries</th>
                    <th className="px-5 py-3">Billing Period</th>
                    <th className="px-5 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {subs.map((sub) => {
                    const pct = sub.usage_percentage;
                    const displayName = sub.user_name || sub.user_email || sub.user_id;
                    const isActioning = actionLoading === sub.user_id;
                    const fb = feedback?.userId === sub.user_id ? feedback : null;

                    return (
                      <tr key={sub.id} className="border-b border-gray-50">
                        {/* User */}
                        <td className="px-5 py-3">
                          <p className="font-medium text-gray-900">{displayName}</p>
                          {sub.user_email && sub.user_name && (
                            <p className="text-xs text-gray-400">{sub.user_email}</p>
                          )}
                        </td>

                        {/* Tier */}
                        <td className="px-5 py-3">
                          <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${TIER_BADGE[sub.tier] ?? "bg-gray-100 text-gray-700"}`}>
                            {sub.tier}
                          </span>
                        </td>

                        {/* Strategic Queries */}
                        <td className="px-5 py-3">
                          {sub.strategic_queries_limit > 0 ? (
                            <div className="w-36">
                              <p className="text-xs text-gray-700">
                                {sub.strategic_queries_used} / {sub.strategic_queries_limit}
                              </p>
                              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-gray-100">
                                <div
                                  className={`h-full rounded-full transition-all ${progressColor(pct)}`}
                                  style={{ width: `${Math.min(100, pct)}%` }}
                                />
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-gray-400">N/A</span>
                          )}
                        </td>

                        {/* Billing Period */}
                        <td className="px-5 py-3 text-xs text-gray-500">
                          {fmtDate(sub.billing_period_start)} &ndash; {fmtDate(sub.billing_period_end)}
                        </td>

                        {/* Actions */}
                        <td className="px-5 py-3">
                          <div className="flex flex-col gap-2">
                            <div className="flex items-center gap-2">
                              {/* Change Tier */}
                              <div className="relative">
                                <button
                                  onClick={() => setTierDropdown(tierDropdown === sub.user_id ? null : sub.user_id)}
                                  disabled={isActioning}
                                  className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                                >
                                  Change Tier
                                </button>
                                {tierDropdown === sub.user_id && (
                                  <div className="absolute right-0 top-full z-10 mt-1 w-36 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                                    {TIERS.map((t) => (
                                      <button
                                        key={t}
                                        onClick={() => handleTierChange(sub.user_id, t)}
                                        className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs hover:bg-gray-50 ${sub.tier === t ? "font-semibold text-blue-600" : "text-gray-700"}`}
                                      >
                                        <span className={`h-2 w-2 rounded-full ${t === "starter" ? "bg-gray-400" : t === "professional" ? "bg-blue-400" : "bg-purple-400"}`} />
                                        <span className="capitalize">{t}</span>
                                        {sub.tier === t && <span className="ml-auto text-blue-600">&#10003;</span>}
                                      </button>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {/* Reset Usage */}
                              <button
                                onClick={() => setResetConfirm(resetConfirm === sub.user_id ? null : sub.user_id)}
                                disabled={isActioning}
                                className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                              >
                                Reset Usage
                              </button>

                              {isActioning && (
                                <svg className="h-4 w-4 animate-spin text-gray-400" viewBox="0 0 24 24" fill="none">
                                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                                </svg>
                              )}
                            </div>

                            {/* Reset confirmation */}
                            {resetConfirm === sub.user_id && (
                              <div className="rounded-md border border-yellow-200 bg-yellow-50 p-2.5">
                                <p className="text-xs text-yellow-800">
                                  Reset usage for <span className="font-medium">{displayName}</span>?
                                  This resets their count to 0 and starts a new 30-day billing period.
                                </p>
                                <div className="mt-2 flex gap-2">
                                  <button
                                    onClick={() => handleResetUsage(sub.user_id)}
                                    className="rounded-md bg-yellow-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-yellow-700"
                                  >
                                    Confirm
                                  </button>
                                  <button
                                    onClick={() => setResetConfirm(null)}
                                    className="rounded-md border border-gray-200 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            )}

                            {/* Inline feedback */}
                            {fb && (
                              <p className={`text-xs font-medium ${fb.type === "success" ? "text-green-600" : "text-red-600"}`}>
                                {fb.message}
                              </p>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ─────────────────────────────────────────────────────────

function SummaryCard({
  label,
  value,
  badgeClass,
}: {
  label: string;
  value: number;
  badgeClass?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-5 py-4 shadow-sm">
      <div className="flex items-center gap-2">
        <p className="text-xs font-medium text-gray-500">{label}</p>
        {badgeClass && (
          <span className={`inline-block h-2 w-2 rounded-full ${badgeClass.replace(/text-\S+/, "").trim()}`} />
        )}
      </div>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
