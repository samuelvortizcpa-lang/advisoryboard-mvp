"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  createCommunicationsApi,
  createNotificationsApi,
  createRagApi,
  NotificationPreferences,
} from "@/lib/api";

const settingsCards = [
  {
    title: "Integrations / Email Sync",
    description: "Connect email accounts and configure routing rules",
    href: "/dashboard/settings/integrations",
  },
  {
    title: "Usage Analytics",
    description: "View AI query history, costs, and usage trends across all clients.",
    href: "/dashboard/settings/usage",
  },
  {
    title: "Subscription Management",
    description: "Manage user tiers, AI query quotas, and billing periods.",
    href: "/dashboard/settings/subscriptions",
  },
];

export default function SettingsPage() {
  const { getToken } = useAuth();
  const [backfillLoading, setBackfillLoading] = useState(false);
  const [backfillResult, setBackfillResult] = useState<string | null>(null);
  const [backfillError, setBackfillError] = useState<string | null>(null);

  // Scheduling URL state
  const [schedulingUrl, setSchedulingUrl] = useState("");
  const [schedulingSaving, setSchedulingSaving] = useState(false);
  const [schedulingResult, setSchedulingResult] = useState<string | null>(null);
  const [schedulingError, setSchedulingError] = useState<string | null>(null);

  // Notification preferences state
  const [notifPrefs, setNotifPrefs] = useState<NotificationPreferences | null>(null);
  const [notifLoading, setNotifLoading] = useState(true);
  const [notifSaved, setNotifSaved] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    createNotificationsApi(getToken)
      .getPreferences()
      .then((prefs) => { if (!cancelled) { setNotifPrefs(prefs); setNotifLoading(false); } })
      .catch(() => { if (!cancelled) setNotifLoading(false); });
    return () => { cancelled = true; };
  }, [getToken]);

  async function updateNotifPref(field: keyof NotificationPreferences, value: boolean | number) {
    if (!notifPrefs) return;
    const prev = { ...notifPrefs };
    setNotifPrefs({ ...notifPrefs, [field]: value });
    setNotifSaved(null);
    try {
      const updated = await createNotificationsApi(getToken).updatePreferences({ [field]: value });
      setNotifPrefs(updated);
      setNotifSaved("Saved");
      setTimeout(() => setNotifSaved(null), 2000);
    } catch {
      setNotifPrefs(prev);
    }
  }

  async function handleBackfill() {
    setBackfillLoading(true);
    setBackfillResult(null);
    setBackfillError(null);
    try {
      const res = await createRagApi(getToken).backfillPages();
      setBackfillResult(res.message);
    } catch (err) {
      setBackfillError(
        err instanceof Error ? err.message : "Backfill failed"
      );
    } finally {
      setBackfillLoading(false);
    }
  }

  async function handleSaveSchedulingUrl() {
    setSchedulingSaving(true);
    setSchedulingResult(null);
    setSchedulingError(null);
    try {
      const res = await createCommunicationsApi(getToken).updateSchedulingUrl(
        schedulingUrl.trim() || null
      );
      setSchedulingResult(
        res.scheduling_url ? "Scheduling link saved" : "Scheduling link cleared"
      );
    } catch (err) {
      setSchedulingError(
        err instanceof Error ? err.message : "Failed to save"
      );
    } finally {
      setSchedulingSaving(false);
    }
  }

  return (
    <div className="px-8 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Configuration
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your workspace preferences and integrations
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {settingsCards.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="group rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50"
          >
            <h2 className="text-base font-semibold text-gray-900 transition-colors group-hover:text-blue-700">
              {card.title}
            </h2>
            <p className="mt-1 text-sm text-gray-500 transition-colors group-hover:text-blue-600">
              {card.description}
            </p>
          </Link>
        ))}

        {/* Meeting Scheduling Link card */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900">
            Meeting Scheduling Link
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Your Calendly, Cal.com, or other scheduling link. Automatically
            included in meeting request emails.
          </p>
          <input
            type="url"
            value={schedulingUrl}
            onChange={(e) => setSchedulingUrl(e.target.value)}
            placeholder="https://calendly.com/your-name"
            className="mt-3 w-full rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 outline-none transition focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          />
          <button
            onClick={handleSaveSchedulingUrl}
            disabled={schedulingSaving}
            className="mt-3 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {schedulingSaving ? (
              <>
                <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                Saving…
              </>
            ) : (
              "Save"
            )}
          </button>
          {schedulingResult && (
            <p className="mt-3 text-sm text-green-600">{schedulingResult}</p>
          )}
          {schedulingError && (
            <p className="mt-3 text-sm text-red-600">{schedulingError}</p>
          )}
        </div>

        {/* Reprocess PDF Pages card */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-gray-900">
            Reprocess PDF Pages
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Generate page thumbnails for PDFs uploaded before the page image
            feature was added.
          </p>
          <button
            onClick={handleBackfill}
            disabled={backfillLoading}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {backfillLoading ? (
              <>
                <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
                Processing…
              </>
            ) : (
              "Reprocess PDF Pages"
            )}
          </button>
          {backfillResult && (
            <p className="mt-3 text-sm text-green-600">{backfillResult}</p>
          )}
          {backfillError && (
            <p className="mt-3 text-sm text-red-600">{backfillError}</p>
          )}
        </div>
      </div>

      {/* Notification Preferences */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-gray-900">
              Email Notifications
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Control which email notifications you receive for this workspace.
            </p>
          </div>
          {notifSaved && (
            <span className="text-xs font-medium text-green-600">{notifSaved}</span>
          )}
        </div>

        {notifLoading ? (
          <div className="mt-6 flex items-center gap-2 text-sm text-gray-400">
            <span className="h-3.5 w-3.5 rounded-full border-2 border-gray-300 border-t-transparent animate-spin" />
            Loading preferences…
          </div>
        ) : notifPrefs ? (
          <div className="mt-6 space-y-5">
            <ToggleRow
              label="Email me when a task is assigned to me"
              checked={notifPrefs.task_assigned}
              onChange={(v) => updateNotifPref("task_assigned", v)}
            />
            <ToggleRow
              label="Email me when my assigned task is completed"
              checked={notifPrefs.task_completed}
              onChange={(v) => updateNotifPref("task_completed", v)}
            />
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-700">Deadline reminders</span>
              <div className="flex items-center gap-3">
                <select
                  value={notifPrefs.deadline_reminder_days}
                  onChange={(e) =>
                    updateNotifPref("deadline_reminder_days", Number(e.target.value))
                  }
                  disabled={!notifPrefs.deadline_reminder}
                  className="rounded-md border border-gray-300 px-2 py-1 text-sm text-gray-700 outline-none focus:border-blue-500 disabled:opacity-50"
                >
                  <option value={1}>1 day before</option>
                  <option value={2}>2 days before</option>
                  <option value={3}>3 days before</option>
                </select>
                <Toggle
                  checked={notifPrefs.deadline_reminder}
                  onChange={(v) => updateNotifPref("deadline_reminder", v)}
                />
              </div>
            </div>
            <div className="flex items-center justify-between opacity-50">
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-700">Daily task digest</span>
                <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                  Coming soon
                </span>
              </div>
              <Toggle checked={false} onChange={() => {}} disabled />
            </div>
          </div>
        ) : (
          <p className="mt-6 text-sm text-gray-400">
            Unable to load notification preferences.
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Toggle components
// ---------------------------------------------------------------------------

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 disabled:cursor-not-allowed ${
        checked ? "bg-blue-600" : "bg-gray-200"
      }`}
    >
      <span
        className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition-transform ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-700">{label}</span>
      <Toggle checked={checked} onChange={onChange} />
    </div>
  );
}
