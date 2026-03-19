"use client";

import { useAuth } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, useCallback } from "react";

import {
  createAdminApi,
  createStripeApi,
  createUsageApi,
  AdminSubscription,
  AdminSubscriptionSummary,
  StripeStatus,
  SubscriptionInfo,
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
  free: "bg-emerald-100 text-emerald-700",
  starter: "bg-gray-100 text-gray-700",
  professional: "bg-blue-100 text-blue-700",
  firm: "bg-purple-100 text-purple-700",
};

const TIERS = ["free", "starter", "professional", "firm"] as const;

function progressColor(pct: number) {
  if (pct > 90) return "bg-red-500";
  if (pct > 70) return "bg-yellow-400";
  return "bg-green-500";
}

function barPct(current: number, limit: number | null) {
  if (limit === null || limit === 0) return 0;
  return Math.min(100, (current / limit) * 100);
}

const PRICING = [
  {
    tier: "free",
    price: "$0",
    features: [
      "3 clients",
      "10 documents",
      "50 AI queries/month",
      "All document types",
      "RAG Q&A",
    ],
  },
  {
    tier: "starter",
    price: "$99",
    features: [
      "25 clients",
      "500 documents",
      "GPT-4o-mini only",
      "500MB storage",
    ],
  },
  {
    tier: "professional",
    price: "$149",
    features: [
      "100 clients",
      "5,000 documents",
      "100 strategic queries/mo",
      "10 Opus queries/mo",
      "5GB storage",
    ],
  },
  {
    tier: "firm",
    price: "$249",
    features: [
      "Unlimited clients",
      "Unlimited documents",
      "500 strategic queries/mo",
      "50 Opus queries/mo",
      "25GB storage",
    ],
  },
] as const;

// ─── Page ───────────────────────────────────────────────────────────────────

export default function SubscriptionManagementPage() {
  const { getToken } = useAuth();
  const searchParams = useSearchParams();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subs, setSubs] = useState<AdminSubscription[]>([]);
  const [summary, setSummary] = useState<AdminSubscriptionSummary | null>(null);
  const [stripeStatus, setStripeStatus] = useState<StripeStatus | null>(null);
  const [subInfo, setSubInfo] = useState<SubscriptionInfo | null>(null);

  // Inline interaction state
  const [tierDropdown, setTierDropdown] = useState<string | null>(null);
  const [resetConfirm, setResetConfirm] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ userId: string; message: string; type: "success" | "error" } | null>(null);

  // Stripe checkout state
  const [checkoutTier, setCheckoutTier] = useState<string | null>(null);
  const [portalLoading, setPortalLoading] = useState(false);

  // Banners from URL params
  const showSuccess = searchParams.get("success") === "true";
  const showCanceled = searchParams.get("canceled") === "true";
  const [bannerVisible, setBannerVisible] = useState(true);

  const stripeConfigured = Boolean(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY);

  const showFeedback = (userId: string, message: string, type: "success" | "error") => {
    setFeedback({ userId, message, type });
    setTimeout(() => setFeedback((f) => (f?.userId === userId ? null : f)), 3000);
  };

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const adminApi = createAdminApi(getToken);
      const stripeApi = createStripeApi(getToken);
      const usageApi = createUsageApi(getToken);
      const [s, sum, ss, si] = await Promise.all([
        adminApi.listSubscriptions(),
        adminApi.subscriptionSummary(),
        stripeApi.status().catch(() => null),
        usageApi.subscription().catch(() => null),
      ]);
      setSubs(s);
      setSummary(sum);
      setStripeStatus(ss);
      setSubInfo(si);
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

  async function handleCheckout(tier: string) {
    setCheckoutTier(tier);
    try {
      const { url } = await createStripeApi(getToken).createCheckout(tier);
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create checkout");
      setCheckoutTier(null);
    }
  }

  async function handleManageBilling() {
    setPortalLoading(true);
    try {
      const { url } = await createStripeApi(getToken).createPortal();
      window.location.href = url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "No Stripe subscription found. Subscribe to a plan first.");
      setPortalLoading(false);
    }
  }

  // ── Loading ─────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6 animate-pulse">
        <div className="mx-auto max-w-6xl space-y-6">
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
        <div className="mx-auto max-w-6xl">
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

  const currentTier = stripeStatus?.tier ?? subInfo?.tier ?? subs[0]?.tier ?? "free";
  const isFreeTier = currentTier === "free";

  // Determine if any limit is > 80% for upgrade prompt
  const showUpgradePrompt = isFreeTier && subInfo && (
    (subInfo.max_clients !== null && subInfo.current_clients / subInfo.max_clients > 0.8) ||
    (subInfo.max_documents !== null && subInfo.current_documents / subInfo.max_documents > 0.8) ||
    (subInfo.strategic_queries_limit > 0 && subInfo.strategic_queries_used / subInfo.strategic_queries_limit > 0.8)
  );

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-6xl space-y-6">

        {/* ── Success/Cancel Banners ────────────────────────────────────── */}
        {bannerVisible && showSuccess && (
          <div className="flex items-center justify-between rounded-xl border border-green-200 bg-green-50 px-5 py-3">
            <p className="text-sm font-medium text-green-700">Subscription updated successfully!</p>
            <button onClick={() => setBannerVisible(false)} className="text-green-500 hover:text-green-700">
              <XIcon />
            </button>
          </div>
        )}
        {bannerVisible && showCanceled && (
          <div className="flex items-center justify-between rounded-xl border border-yellow-200 bg-yellow-50 px-5 py-3">
            <p className="text-sm font-medium text-yellow-700">Checkout canceled. No changes were made.</p>
            <button onClick={() => setBannerVisible(false)} className="text-yellow-500 hover:text-yellow-700">
              <XIcon />
            </button>
          </div>
        )}

        {/* ── Header ────────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Subscription Management</h1>
            <p className="mt-1 text-sm text-gray-500">Manage your plan and monitor usage limits</p>
          </div>
          {stripeConfigured && stripeStatus?.stripe_customer_id && (
            <button
              onClick={handleManageBilling}
              disabled={portalLoading}
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3.5 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
            >
              {portalLoading ? "Loading\u2026" : "Manage Billing"}
            </button>
          )}
        </div>

        {/* ── Usage Limits ───────────────────────────────────────────────── */}
        {subInfo && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Usage Limits</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <UsageBar
                label="Clients"
                current={subInfo.current_clients}
                limit={subInfo.max_clients}
              />
              <UsageBar
                label="Documents"
                current={subInfo.current_documents}
                limit={subInfo.max_documents}
              />
              <UsageBar
                label="AI Queries"
                current={subInfo.strategic_queries_used}
                limit={subInfo.strategic_queries_limit > 0 ? subInfo.strategic_queries_limit : null}
                suffix="this billing period"
              />
              {(currentTier === "professional" || currentTier === "firm") && (
                <UsageBar
                  label="Opus Queries"
                  current={0}
                  limit={currentTier === "professional" ? 10 : 50}
                  suffix="this billing period"
                />
              )}
            </div>
            {showUpgradePrompt && (
              <p className="mt-4 text-xs text-amber-600 font-medium">
                Running low on capacity?{" "}
                <span className="underline cursor-pointer" onClick={() => document.getElementById("pricing-section")?.scrollIntoView({ behavior: "smooth" })}>
                  Upgrade for more
                </span>
              </p>
            )}
          </div>
        )}

        {/* ── Pricing Cards ─────────────────────────────────────────────── */}
        <div id="pricing-section">
          {stripeConfigured ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {PRICING.map((plan) => {
                const isCurrent = currentTier === plan.tier;
                const isFreeCard = plan.tier === "free";
                const tierIndex = TIERS.indexOf(plan.tier as typeof TIERS[number]);
                const currentIndex = TIERS.indexOf(currentTier as typeof TIERS[number]);
                const isUpgrade = tierIndex > currentIndex;
                return (
                  <div
                    key={plan.tier}
                    className={`relative rounded-xl border p-5 shadow-sm ${
                      isCurrent
                        ? "border-blue-300 bg-blue-50/50 ring-1 ring-blue-200"
                        : "border-gray-200 bg-white"
                    }`}
                  >
                    {isCurrent && (
                      <span className="absolute -top-2.5 left-4 rounded-full bg-blue-600 px-2.5 py-0.5 text-[10px] font-semibold text-white">
                        Current Plan
                      </span>
                    )}
                    <h3 className="text-sm font-semibold capitalize text-gray-900">{plan.tier}</h3>
                    <p className="mt-1 text-2xl font-bold text-gray-900">
                      {plan.price}<span className="text-sm font-normal text-gray-500">/mo</span>
                    </p>
                    <ul className="mt-3 space-y-1.5">
                      {plan.features.map((f) => (
                        <li key={f} className="flex items-center gap-2 text-xs text-gray-600">
                          <CheckIcon />
                          {f}
                        </li>
                      ))}
                    </ul>
                    {/* Show Upgrade button only on paid cards when user is on a lower tier */}
                    {!isCurrent && !isFreeCard && isUpgrade && (
                      <button
                        onClick={() => handleCheckout(plan.tier)}
                        disabled={checkoutTier !== null}
                        className="mt-4 w-full rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
                      >
                        {checkoutTier === plan.tier ? "Redirecting\u2026" : "Upgrade"}
                      </button>
                    )}
                    {/* For paid users on a higher tier viewing a lower paid card — manage via portal */}
                    {!isCurrent && !isFreeCard && !isUpgrade && stripeStatus?.stripe_customer_id && (
                      <button
                        onClick={handleManageBilling}
                        disabled={portalLoading}
                        className="mt-4 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
                      >
                        Manage Plan
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-xl border border-gray-200 bg-white p-6 text-center shadow-sm">
              <p className="text-sm text-gray-500">Payment processing coming soon</p>
            </div>
          )}
        </div>

        {/* ── Summary Cards ─────────────────────────────────────────────── */}
        {summary && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <SummaryCard label="Total Users" value={summary.total_users} />
            <SummaryCard
              label="Free"
              value={summary.by_tier.free ?? 0}
              badgeClass="bg-emerald-100 text-emerald-700"
            />
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
                                        <span className={`h-2 w-2 rounded-full ${t === "free" ? "bg-emerald-400" : t === "starter" ? "bg-gray-400" : t === "professional" ? "bg-blue-400" : "bg-purple-400"}`} />
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

function UsageBar({
  label,
  current,
  limit,
  suffix,
}: {
  label: string;
  current: number;
  limit: number | null;
  suffix?: string;
}) {
  const pct = barPct(current, limit);
  const isUnlimited = limit === null;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <p className="text-xs font-medium text-gray-700">{label}</p>
        <p className="text-xs text-gray-500">
          {isUnlimited ? (
            <>{current} &mdash; Unlimited</>
          ) : (
            <>
              {current} of {limit}
              {suffix && <span className="text-gray-400 ml-1">{suffix}</span>}
            </>
          )}
        </p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-full rounded-full transition-all ${isUnlimited ? "bg-green-500" : progressColor(pct)}`}
          style={{ width: isUnlimited ? "5%" : `${Math.max(2, pct)}%` }}
        />
      </div>
    </div>
  );
}

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

function CheckIcon() {
  return (
    <svg className="h-3.5 w-3.5 flex-shrink-0 text-green-500" viewBox="0 0 20 20" fill="currentColor">
      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
