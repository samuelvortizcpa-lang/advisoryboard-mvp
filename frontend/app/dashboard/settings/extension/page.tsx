"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import {
  Client,
  ExtensionCapture,
  ExtensionCaptureStats,
  ExtensionConfig,
  MonitoringRule,
  MonitoringRuleCreate,
  MonitoringRuleUpdate,
  createClientsApi,
  createExtensionApi,
} from "@/lib/api";
import StatCard from "@/components/ui/StatCard";
import ThinProgress from "@/components/ui/ThinProgress";

// ─── Rule type labels ────────────────────────────────────────────────────────

const RULE_TYPE_LABELS: Record<string, string> = {
  domain: "Domain",
  url_contains: "URL Contains",
  url_pattern: "URL Pattern",
  page_title: "Page Title",
  page_content: "Page Content",
  email_from: "Email From",
  email_sender: "Email Sender",
};

// ─── Main page ───────────────────────────────────────────────────────────────

export default function ExtensionSettingsPage() {
  const { getToken } = useAuth();

  // ── Data state ──
  const [config, setConfig] = useState<ExtensionConfig | null>(null);
  const [captures, setCaptures] = useState<ExtensionCapture[]>([]);
  const [stats, setStats] = useState<ExtensionCaptureStats | null>(null);
  const [rules, setRules] = useState<MonitoringRule[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Feedback banner ──
  const [feedback, setFeedback] = useState<{
    msg: string;
    type: "success" | "error";
  } | null>(null);

  // ── Rule modal ──
  const [showRuleModal, setShowRuleModal] = useState(false);
  const [editingRule, setEditingRule] = useState<MonitoringRule | null>(null);
  const [ruleForm, setRuleForm] = useState<MonitoringRuleCreate>({
    rule_name: "",
    rule_type: "domain",
    pattern: "",
    client_id: "",
    notify_only: false,
  });
  const [saving, setSaving] = useState(false);

  // ── Auto-dismiss feedback ──
  useEffect(() => {
    if (!feedback) return;
    const t = setTimeout(() => setFeedback(null), 4000);
    return () => clearTimeout(t);
  }, [feedback]);

  // ── Load data ──
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const extApi = createExtensionApi(getToken);
      const clientsApi = createClientsApi(getToken);

      const [configRes, capturesRes, statsRes, rulesRes, clientsRes] =
        await Promise.all([
          extApi.getConfig(),
          extApi.getRecentCaptures(20),
          extApi.getCaptureStats(),
          extApi.getMonitoringRules(),
          clientsApi.list(0, 200),
        ]);

      setConfig(configRes);
      setCaptures(capturesRes);
      setStats(statsRes);
      setRules(rulesRes);
      setClients(clientsRes.items ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load extension data");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Rule CRUD ──
  const openCreateRule = () => {
    setEditingRule(null);
    setRuleForm({
      rule_name: "",
      rule_type: "domain",
      pattern: "",
      client_id: "",
      notify_only: false,
    });
    setShowRuleModal(true);
  };

  const openEditRule = (rule: MonitoringRule) => {
    setEditingRule(rule);
    setRuleForm({
      rule_name: rule.rule_name,
      rule_type: rule.rule_type,
      pattern: rule.pattern,
      client_id: rule.client_id,
      notify_only: rule.notify_only,
    });
    setShowRuleModal(true);
  };

  const handleSaveRule = async () => {
    if (!ruleForm.rule_name || !ruleForm.pattern || !ruleForm.client_id) return;
    setSaving(true);
    try {
      const api = createExtensionApi(getToken);
      if (editingRule) {
        const update: MonitoringRuleUpdate = { ...ruleForm };
        await api.updateMonitoringRule(editingRule.id, update);
        setFeedback({ msg: "Rule updated", type: "success" });
      } else {
        await api.createMonitoringRule(ruleForm);
        setFeedback({ msg: "Rule created", type: "success" });
      }
      setShowRuleModal(false);
      await loadData();
    } catch {
      setFeedback({ msg: "Failed to save rule", type: "error" });
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      const api = createExtensionApi(getToken);
      await api.deleteMonitoringRule(ruleId);
      setFeedback({ msg: "Rule deleted", type: "success" });
      await loadData();
    } catch {
      setFeedback({ msg: "Failed to delete rule", type: "error" });
    }
  };

  const handleToggleRule = async (rule: MonitoringRule) => {
    try {
      const api = createExtensionApi(getToken);
      await api.updateMonitoringRule(rule.id, { is_active: !rule.is_active });
      await loadData();
    } catch {
      setFeedback({ msg: "Failed to toggle rule", type: "error" });
    }
  };

  // ── Render ──
  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
          {error}
        </div>
      </div>
    );
  }

  const activeRules = rules.filter((r) => r.is_active).length;
  const captureLimit = config?.captures_per_day;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Extension Settings
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your Callwen browser extension, capture history, and
            monitoring rules.
          </p>
        </div>

        {/* Feedback banner */}
        {feedback && (
          <div
            className={`rounded-lg px-4 py-3 text-sm font-medium ${
              feedback.type === "success"
                ? "bg-green-50 text-green-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            {feedback.msg}
          </div>
        )}

        {/* ── Extension Status Banner ── */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className={`h-3 w-3 rounded-full ${
                  config ? "bg-green-500" : "bg-gray-300"
                }`}
              />
              <div>
                <p className="font-medium text-gray-900">
                  Browser Extension
                </p>
                <p className="text-sm text-gray-500">
                  {config
                    ? `${config.tier.charAt(0).toUpperCase() + config.tier.slice(1)} tier`
                    : "Not configured"}
                </p>
              </div>
            </div>
            <div className="flex gap-4 text-sm text-gray-500">
              {config?.auto_match && (
                <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                  Auto-Match
                </span>
              )}
              {config?.monitoring && (
                <span className="rounded-full bg-purple-50 px-2.5 py-0.5 text-xs font-medium text-purple-700">
                  Monitoring
                </span>
              )}
              {config?.parsers && (
                <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700">
                  Parsers
                </span>
              )}
            </div>
          </div>
          {captureLimit != null && (
            <div className="mt-4">
              <ThinProgress
                label="Daily captures"
                current={config?.captures_today ?? 0}
                max={captureLimit}
              />
            </div>
          )}
        </div>

        {/* ── Capture Analytics ── */}
        <div>
          <h2 className="mb-3 text-lg font-semibold text-gray-900">
            Capture Analytics
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard
              label="Today"
              value={stats?.today_count ?? 0}
              context={
                captureLimit != null
                  ? `${config?.captures_remaining ?? 0} remaining`
                  : "Unlimited"
              }
              contextType={
                captureLimit != null &&
                (config?.captures_remaining ?? 0) < 5
                  ? "warning"
                  : "muted"
              }
            />
            <StatCard
              label="This Month"
              value={stats?.month_count ?? 0}
            />
            <StatCard
              label="Active Rules"
              value={activeRules}
              context={`${rules.length} total`}
              contextType="muted"
            />
          </div>

          {/* Top clients */}
          {stats?.top_clients && stats.top_clients.length > 0 && (
            <div className="mt-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-medium text-gray-700">
                Top Clients by Captures
              </h3>
              <div className="space-y-2">
                {stats.top_clients.map((c) => (
                  <div
                    key={c.client_id}
                    className="flex items-center justify-between text-sm"
                  >
                    <span className="text-gray-700">{c.client_name}</span>
                    <span className="font-medium text-gray-900">
                      {c.capture_count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Recent Captures ── */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">
            Recent Captures
          </h2>
          {captures.length === 0 ? (
            <p className="text-sm text-gray-400">No captures yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs text-gray-500">
                    <th className="pb-2 font-medium">File</th>
                    <th className="pb-2 font-medium">Client</th>
                    <th className="pb-2 font-medium">Type</th>
                    <th className="pb-2 font-medium">Date</th>
                    <th className="pb-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {captures.map((c) => (
                    <tr
                      key={c.document_id}
                      className="border-b border-gray-50"
                    >
                      <td className="py-2 pr-3">
                        <span
                          className="max-w-[200px] truncate text-gray-700"
                          title={c.filename}
                        >
                          {c.filename}
                        </span>
                      </td>
                      <td className="py-2 pr-3 text-gray-600">
                        {c.client_name}
                      </td>
                      <td className="py-2 pr-3 text-gray-500">
                        {c.capture_type ?? "—"}
                      </td>
                      <td className="py-2 pr-3 text-gray-500">
                        {new Date(c.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-2">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            c.processed
                              ? "bg-green-50 text-green-700"
                              : "bg-amber-50 text-amber-700"
                          }`}
                        >
                          {c.processed ? "Processed" : "Pending"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Monitoring Rules ── */}
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">
              Monitoring Rules
            </h2>
            <button
              onClick={openCreateRule}
              className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
            >
              + Add Rule
            </button>
          </div>

          {rules.length === 0 ? (
            <p className="text-sm text-gray-400">
              No monitoring rules configured.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-xs text-gray-500">
                    <th className="pb-2 font-medium">Name</th>
                    <th className="pb-2 font-medium">Type</th>
                    <th className="pb-2 font-medium">Pattern</th>
                    <th className="pb-2 font-medium">Client</th>
                    <th className="pb-2 font-medium">Mode</th>
                    <th className="pb-2 font-medium">Active</th>
                    <th className="pb-2 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr
                      key={rule.id}
                      className="border-b border-gray-50"
                    >
                      <td className="py-2 pr-3 font-medium text-gray-700">
                        {rule.rule_name}
                      </td>
                      <td className="py-2 pr-3 text-gray-500">
                        {RULE_TYPE_LABELS[rule.rule_type] ?? rule.rule_type}
                      </td>
                      <td className="py-2 pr-3">
                        <code className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
                          {rule.pattern}
                        </code>
                      </td>
                      <td className="py-2 pr-3 text-gray-600">
                        {rule.client_name ?? "—"}
                      </td>
                      <td className="py-2 pr-3">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                            rule.notify_only
                              ? "bg-yellow-50 text-yellow-700"
                              : "bg-blue-50 text-blue-700"
                          }`}
                        >
                          {rule.notify_only ? "Notify" : "Capture"}
                        </span>
                      </td>
                      <td className="py-2 pr-3">
                        <button
                          onClick={() => handleToggleRule(rule)}
                          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                            rule.is_active ? "bg-blue-600" : "bg-gray-300"
                          }`}
                        >
                          <span
                            className={`inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform ${
                              rule.is_active
                                ? "translate-x-4"
                                : "translate-x-0.5"
                            }`}
                          />
                        </button>
                      </td>
                      <td className="py-2">
                        <div className="flex gap-2">
                          <button
                            onClick={() => openEditRule(rule)}
                            className="text-xs text-blue-600 hover:text-blue-800"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteRule(rule.id)}
                            className="text-xs text-red-500 hover:text-red-700"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Auto-Match Statistics ── */}
        {config?.auto_match && stats?.top_clients && (
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-lg font-semibold text-gray-900">
              Auto-Match Statistics
            </h2>
            <p className="mb-3 text-sm text-gray-500">
              Pages automatically matched to clients based on URL patterns and
              page content.
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <StatCard
                label="Matched Today"
                value={stats.today_count}
              />
              <StatCard
                label="Matched This Month"
                value={stats.month_count}
              />
            </div>
          </div>
        )}

        {/* ── Rule Modal ── */}
        {showRuleModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
              <h3 className="mb-4 text-lg font-semibold text-gray-900">
                {editingRule ? "Edit Rule" : "Create Rule"}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Rule Name
                  </label>
                  <input
                    type="text"
                    value={ruleForm.rule_name}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, rule_name: e.target.value })
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="e.g. Monitor IRS updates"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Rule Type
                  </label>
                  <select
                    value={ruleForm.rule_type}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, rule_type: e.target.value })
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    {Object.entries(RULE_TYPE_LABELS).map(([val, lbl]) => (
                      <option key={val} value={val}>
                        {lbl}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Pattern
                  </label>
                  <input
                    type="text"
                    value={ruleForm.pattern}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, pattern: e.target.value })
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="e.g. irs.gov"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Client
                  </label>
                  <select
                    value={ruleForm.client_id}
                    onChange={(e) =>
                      setRuleForm({ ...ruleForm, client_id: e.target.value })
                    }
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                  >
                    <option value="">Select a client...</option>
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="notify-only"
                    checked={ruleForm.notify_only ?? false}
                    onChange={(e) =>
                      setRuleForm({
                        ...ruleForm,
                        notify_only: e.target.checked,
                      })
                    }
                    className="h-4 w-4 rounded border-gray-300 text-blue-600"
                  />
                  <label
                    htmlFor="notify-only"
                    className="text-sm text-gray-700"
                  >
                    Notify only (don&apos;t auto-capture)
                  </label>
                </div>
              </div>

              <div className="mt-6 flex justify-end gap-3">
                <button
                  onClick={() => setShowRuleModal(false)}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveRule}
                  disabled={
                    saving ||
                    !ruleForm.rule_name ||
                    !ruleForm.pattern ||
                    !ruleForm.client_id
                  }
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving
                    ? "Saving..."
                    : editingRule
                      ? "Update Rule"
                      : "Create Rule"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
