"use client";

import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert, createAlertsApi } from "@/lib/api";

const SEVERITY_CONFIG: Record<string, { border: string; bg: string; icon: string; iconBg: string; label: string }> = {
  critical: {
    border: "border-l-red-500",
    bg: "bg-red-50",
    icon: "text-red-600",
    iconBg: "bg-red-100",
    label: "Critical",
  },
  warning: {
    border: "border-l-amber-400",
    bg: "bg-amber-50",
    icon: "text-amber-600",
    iconBg: "bg-amber-100",
    label: "Warning",
  },
  info: {
    border: "border-l-blue-400",
    bg: "bg-blue-50",
    icon: "text-blue-600",
    iconBg: "bg-blue-100",
    label: "Info",
  },
};

export default function AlertsList() {
  const { getToken } = useAuth();
  const router = useRouter();

  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [dismissing, setDismissing] = useState<string | null>(null);

  useEffect(() => {
    createAlertsApi(getToken)
      .list()
      .then((res) => setAlerts(res.alerts))
      .catch(() => {/* non-fatal */})
      .finally(() => setLoading(false));
  }, [getToken]);

  async function handleDismiss(alert: Alert) {
    setDismissing(alert.id);
    try {
      await createAlertsApi(getToken).dismiss(alert.type, alert.related_id);
      setAlerts((prev) => prev.filter((a) => !(a.type === alert.type && a.related_id === alert.related_id)));
    } catch {
      // non-fatal
    } finally {
      setDismissing(null);
    }
  }

  function handleNavigate(alert: Alert) {
    const tab = alert.type === "consent_needed" || alert.type === "consent_expiring"
      ? "overview"
      : "actions";
    router.push(`/dashboard/clients/${alert.client_id}?tab=${tab}`);
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-600 border-t-transparent" />
          <span className="text-sm text-gray-400">Loading alerts…</span>
        </div>
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-green-50">
            <CheckCircleIcon />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">All clear</p>
            <p className="text-xs text-gray-500">No alerts at this time — you&apos;re all caught up!</p>
          </div>
        </div>
      </div>
    );
  }

  const criticalCount = alerts.filter((a) => a.severity === "critical").length;
  const warningCount = alerts.filter((a) => a.severity === "warning").length;

  return (
    <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-50">
            <BellIcon />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Smart Alerts</h2>
            <p className="text-xs text-gray-500">
              {alerts.length} alert{alerts.length !== 1 ? "s" : ""}
              {criticalCount > 0 && (
                <span className="ml-1.5 inline-flex items-center rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700">
                  {criticalCount} critical
                </span>
              )}
              {warningCount > 0 && (
                <span className="ml-1 inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700">
                  {warningCount} warning
                </span>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Alert list */}
      <ul className="divide-y divide-gray-50">
        {alerts.map((alert) => {
          const config = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.info;
          const isDismissing = dismissing === alert.id;

          return (
            <li
              key={`${alert.type}-${alert.related_id}`}
              className={`flex items-start gap-3 border-l-4 px-5 py-3.5 transition-colors hover:bg-gray-50 ${config.border}`}
            >
              {/* Icon */}
              <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${config.iconBg}`}>
                <SeverityIcon severity={alert.severity} alertType={alert.type} />
              </div>

              {/* Content */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleNavigate(alert)}
                    className="text-xs font-semibold text-blue-600 hover:underline"
                  >
                    {alert.client_name}
                  </button>
                  <span className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${config.bg} ${config.icon}`}>
                    {SEVERITY_CONFIG[alert.severity]?.label}
                  </span>
                </div>
                <p className="mt-0.5 text-sm text-gray-700 leading-snug">{alert.message}</p>
                <p className="mt-1 text-[11px] text-gray-400">
                  {formatAlertDate(alert.created_at)}
                </p>
              </div>

              {/* Dismiss */}
              <button
                onClick={() => handleDismiss(alert)}
                disabled={isDismissing}
                title="Dismiss alert"
                className="mt-1 shrink-0 rounded-md p-1 text-gray-300 transition-colors hover:bg-gray-100 hover:text-gray-500 disabled:opacity-40"
              >
                {isDismissing ? <SmallSpinner /> : <XIcon />}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatAlertDate(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;
  const diffMs = Date.now() - date.getTime();
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffDays < 0) {
    const absDays = Math.abs(diffDays);
    if (absDays === 0) return "Today";
    if (absDays === 1) return "Tomorrow";
    return `In ${absDays} days`;
  }
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function BellIcon() {
  return (
    <svg className="h-4 w-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  );
}

function CheckCircleIcon() {
  return (
    <svg className="h-5 w-5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function SmallSpinner() {
  return (
    <span className="block h-3.5 w-3.5 animate-spin rounded-full border-2 border-gray-300 border-t-transparent" />
  );
}

function SeverityIcon({ severity, alertType }: { severity: string; alertType?: string }) {
  // Shield icon for consent-related alerts
  if (alertType === "consent_needed" || alertType === "consent_expiring") {
    const color = alertType === "consent_needed" ? "text-amber-600" : "text-blue-600";
    return (
      <svg className={`h-3.5 w-3.5 ${color}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    );
  }

  if (severity === "critical") {
    return (
      <svg className="h-3.5 w-3.5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
      </svg>
    );
  }
  if (severity === "warning") {
    return (
      <svg className="h-3.5 w-3.5 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );
  }
  return (
    <svg className="h-3.5 w-3.5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
    </svg>
  );
}
