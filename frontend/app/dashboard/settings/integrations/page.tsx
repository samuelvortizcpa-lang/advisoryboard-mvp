"use client";

import { useAuth } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  Client,
  IntegrationConnection,
  RoutingRule,
  SyncLog,
  createClientsApi,
  createIntegrationsApi,
} from "@/lib/api";

// ─── Main page ────────────────────────────────────────────────────────────────

export default function IntegrationsSettingsPage() {
  const { getToken } = useAuth();
  const searchParams = useSearchParams();

  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [clients, setClients] = useState<Client[]>([]);
  const [syncHistories, setSyncHistories] = useState<
    Record<string, SyncLog[]>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Success banner ──
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // ── Sync state per connection ──
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set());
  const [syncResults, setSyncResults] = useState<Record<string, SyncLog>>({});

  // ── Add-rule form ──
  const [showAddRule, setShowAddRule] = useState(false);
  const [newRuleEmail, setNewRuleEmail] = useState("");
  const [newRuleClientId, setNewRuleClientId] = useState("");
  const [newRuleMatchType, setNewRuleMatchType] = useState("from");
  const [addingRule, setAddingRule] = useState(false);

  // ── Auto-generate state ──
  const [autoGenerating, setAutoGenerating] = useState(false);

  // ── History expand ──
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(
    null
  );

  // ── Connecting ──
  const [connecting, setConnecting] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const api = createIntegrationsApi(getToken);
      const clientsApi = createClientsApi(getToken);
      const [conns, rls, clientList] = await Promise.all([
        api.listConnections(),
        api.listRoutingRules(),
        clientsApi.list(0, 200),
      ]);
      setConnections(conns);
      setRules(rls);
      setClients(clientList.items);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Check for OAuth callback params
  useEffect(() => {
    if (searchParams.get("integration_connected") === "google") {
      setSuccessMsg("Gmail connected successfully! Set up routing rules below to start syncing emails.");
      // Reload to pick up new connection
      loadData();
    }
    if (searchParams.get("integration_error")) {
      setError("Failed to connect Gmail. Please try again.");
    }
  }, [searchParams, loadData]);

  // ── Handlers ──

  const handleConnectGmail = async () => {
    setConnecting(true);
    try {
      const api = createIntegrationsApi(getToken);
      const { authorization_url } = await api.getGoogleAuthUrl();
      window.location.href = authorization_url;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to get auth URL");
      setConnecting(false);
    }
  };

  const handleDisconnect = async (connectionId: string) => {
    try {
      const api = createIntegrationsApi(getToken);
      await api.disconnect(connectionId);
      setConnections((prev) => prev.filter((c) => c.id !== connectionId));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to disconnect");
    }
  };

  const handleSync = async (connectionId: string) => {
    setSyncingIds((prev) => new Set(prev).add(connectionId));
    try {
      const api = createIntegrationsApi(getToken);
      const log = await api.triggerSync(connectionId);
      setSyncResults((prev) => ({ ...prev, [connectionId]: log }));
      // Refresh connections to update last_sync_at
      const conns = await api.listConnections();
      setConnections(conns);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(connectionId);
        return next;
      });
    }
  };

  const handleDeepSync = async (connectionId: string) => {
    setSyncingIds((prev) => new Set(prev).add(connectionId));
    try {
      const api = createIntegrationsApi(getToken);
      const log = await api.triggerDeepSync(connectionId);
      setSyncResults((prev) => ({ ...prev, [connectionId]: log }));
      const conns = await api.listConnections();
      setConnections(conns);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Deep sync failed");
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(connectionId);
        return next;
      });
    }
  };

  const handleLoadHistory = async (connectionId: string) => {
    if (expandedHistoryId === connectionId) {
      setExpandedHistoryId(null);
      return;
    }
    try {
      const api = createIntegrationsApi(getToken);
      const logs = await api.getSyncHistory(connectionId);
      setSyncHistories((prev) => ({ ...prev, [connectionId]: logs }));
      setExpandedHistoryId(connectionId);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load sync history");
    }
  };

  const handleAddRule = async () => {
    if (!newRuleEmail || !newRuleClientId) return;
    setAddingRule(true);
    try {
      const api = createIntegrationsApi(getToken);
      const rule = await api.createRoutingRule({
        email_address: newRuleEmail,
        client_id: newRuleClientId,
        match_type: newRuleMatchType,
      });
      setRules((prev) => [...prev, rule]);
      setNewRuleEmail("");
      setNewRuleClientId("");
      setNewRuleMatchType("from");
      setShowAddRule(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create rule");
    } finally {
      setAddingRule(false);
    }
  };

  const handleDeleteRule = async (ruleId: string) => {
    try {
      const api = createIntegrationsApi(getToken);
      await api.deleteRoutingRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete rule");
    }
  };

  const handleAutoGenerate = async () => {
    setAutoGenerating(true);
    try {
      const api = createIntegrationsApi(getToken);
      const newRules = await api.autoGenerateRules();
      if (newRules.length === 0) {
        setSuccessMsg("No new rules to generate. All client emails already have routing rules.");
      } else {
        setRules((prev) => [...prev, ...newRules]);
        setSuccessMsg(`Auto-generated ${newRules.length} routing rule${newRules.length > 1 ? "s" : ""} from client emails.`);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to auto-generate rules");
    } finally {
      setAutoGenerating(false);
    }
  };

  // ── Render ──

  if (loading) {
    return (
      <div className="flex items-center justify-center px-8 py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-blue-600" />
      </div>
    );
  }

  return (
    <div className="px-8 py-8 space-y-6">
      {/* Header */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Settings
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">Integrations</h1>
        <p className="mt-1 text-sm text-gray-500">
          Connect email accounts and configure how incoming emails are routed to
          clients.
        </p>
      </div>

      {/* Success banner */}
      {successMsg && (
        <div className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-3">
          <p className="text-sm text-green-800">{successMsg}</p>
          <button
            onClick={() => setSuccessMsg(null)}
            className="text-green-600 hover:text-green-800"
          >
            <XIcon />
          </button>
        </div>
      )}

      {/* Error banner */}
      {error && (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-800">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-red-600 hover:text-red-800"
          >
            <XIcon />
          </button>
        </div>
      )}

      {/* ───────── Connected Accounts ───────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-900">
            Connected Accounts
          </h2>
          {connections.length > 0 && (
            <button
              onClick={handleConnectGmail}
              disabled={connecting}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              + Add Account
            </button>
          )}
        </div>

        <div className="p-6">
          {connections.length === 0 ? (
            /* Empty state */
            <div className="flex flex-col items-center rounded-lg border-2 border-dashed border-gray-200 px-6 py-10">
              <GmailIcon />
              <p className="mt-3 text-sm font-medium text-gray-900">
                No accounts connected
              </p>
              <p className="mt-1 text-xs text-gray-500">
                Connect your Gmail to auto-ingest client emails
              </p>
              <button
                onClick={handleConnectGmail}
                disabled={connecting}
                className="mt-4 inline-flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {connecting ? (
                  <Spinner />
                ) : (
                  <GmailIcon small />
                )}
                Connect Gmail
              </button>
            </div>
          ) : (
            /* Connection cards */
            <div className="space-y-4">
              {connections.map((conn) => {
                const isSyncing = syncingIds.has(conn.id);
                const result = syncResults[conn.id];

                return (
                  <div
                    key={conn.id}
                    className="rounded-lg border border-gray-200 p-4"
                  >
                    <div className="flex items-center justify-between">
                      {/* Left: icon + info */}
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-50">
                          <GmailIcon />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-gray-900">
                            {conn.provider_email || "Gmail"}
                          </p>
                          <p className="text-xs text-gray-500">
                            {conn.last_sync_at
                              ? `Last synced ${formatRelative(conn.last_sync_at)}`
                              : "Never synced"}
                          </p>
                        </div>
                      </div>

                      {/* Right: actions */}
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleSync(conn.id)}
                          disabled={isSyncing}
                          className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
                        >
                          {isSyncing ? <Spinner /> : <SyncIcon />}
                          Sync Now
                        </button>
                        <button
                          onClick={() => handleDeepSync(conn.id)}
                          disabled={isSyncing}
                          className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
                          title="Sync last 7 days (up to 200 emails)"
                        >
                          Deep Sync
                        </button>
                        <button
                          onClick={() => handleLoadHistory(conn.id)}
                          className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
                        >
                          History
                        </button>
                        <button
                          onClick={() => handleDisconnect(conn.id)}
                          className="inline-flex items-center rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50"
                        >
                          Disconnect
                        </button>
                      </div>
                    </div>

                    {/* Sync result */}
                    {result && !isSyncing && (
                      <div className="mt-3 rounded-md border border-gray-100 bg-gray-50 px-4 py-3">
                        <div className="flex items-center gap-4 text-xs">
                          <span
                            className={`inline-flex items-center gap-1 font-medium ${
                              result.status === "completed"
                                ? "text-green-700"
                                : "text-red-700"
                            }`}
                          >
                            <span
                              className={`h-1.5 w-1.5 rounded-full ${
                                result.status === "completed"
                                  ? "bg-green-500"
                                  : "bg-red-500"
                              }`}
                            />
                            {result.status === "completed"
                              ? "Completed"
                              : "Failed"}
                          </span>
                          <span className="text-gray-600">
                            {result.emails_found} found
                          </span>
                          <span className="text-green-700">
                            {result.emails_ingested} ingested
                          </span>
                          <span className="text-gray-500">
                            {result.emails_skipped} skipped
                          </span>
                        </div>
                        {result.error_message && (
                          <p className="mt-1 text-xs text-red-600">
                            {result.error_message}
                          </p>
                        )}
                      </div>
                    )}

                    {/* Sync history */}
                    {expandedHistoryId === conn.id &&
                      syncHistories[conn.id] && (
                        <div className="mt-3">
                          <SyncHistoryTable
                            logs={syncHistories[conn.id]}
                          />
                        </div>
                      )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* ───────── Email Routing Rules ───────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              Email Routing Rules
            </h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Map email addresses to clients so synced emails land in the right
              place
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleAutoGenerate}
              disabled={autoGenerating}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              {autoGenerating ? <Spinner /> : <SparklesIcon />}
              Auto-Generate
            </button>
            <button
              onClick={() => setShowAddRule(!showAddRule)}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700"
            >
              + Add Rule
            </button>
          </div>
        </div>

        <div className="p-6">
          {/* Inline add form */}
          {showAddRule && (
            <div className="mb-4 flex items-end gap-3 rounded-lg border border-blue-100 bg-blue-50/50 p-4">
              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Email Address
                </label>
                <input
                  type="email"
                  value={newRuleEmail}
                  onChange={(e) => setNewRuleEmail(e.target.value)}
                  placeholder="client@example.com"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              <div className="w-48">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Client
                </label>
                <select
                  value={newRuleClientId}
                  onChange={(e) => setNewRuleClientId(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="">Select client...</option>
                  {clients.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="w-32">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Match Type
                </label>
                <select
                  value={newRuleMatchType}
                  onChange={(e) => setNewRuleMatchType(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="from">From</option>
                  <option value="to">To</option>
                  <option value="both">Both</option>
                </select>
              </div>
              <button
                onClick={handleAddRule}
                disabled={addingRule || !newRuleEmail || !newRuleClientId}
                className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {addingRule ? <Spinner /> : "Save"}
              </button>
              <button
                onClick={() => setShowAddRule(false)}
                className="inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          )}

          {rules.length === 0 && !showAddRule ? (
            <div className="flex flex-col items-center rounded-lg border-2 border-dashed border-gray-200 px-6 py-8">
              <p className="text-sm text-gray-500">No routing rules yet</p>
              <p className="mt-1 text-xs text-gray-400">
                Add rules to map email addresses to clients, or auto-generate
                from client emails
              </p>
            </div>
          ) : (
            rules.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase tracking-wide text-gray-400">
                    <th className="pb-2 pr-4">Email Address</th>
                    <th className="pb-2 pr-4">Client</th>
                    <th className="pb-2 pr-4">Match Type</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 w-16"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {rules.map((rule) => (
                    <tr key={rule.id} className="group">
                      <td className="py-2.5 pr-4 font-mono text-xs text-gray-900">
                        {rule.email_address}
                      </td>
                      <td className="py-2.5 pr-4 text-gray-700">
                        {rule.client_name}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 capitalize">
                          {rule.match_type}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4">
                        <span
                          className={`inline-flex items-center gap-1 text-xs font-medium ${
                            rule.is_active
                              ? "text-green-700"
                              : "text-gray-400"
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              rule.is_active
                                ? "bg-green-500"
                                : "bg-gray-300"
                            }`}
                          />
                          {rule.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="py-2.5">
                        <button
                          onClick={() => handleDeleteRule(rule.id)}
                          className="invisible text-xs text-red-500 hover:text-red-700 group-hover:visible"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          )}
        </div>
      </section>
    </div>
  );
}

// ─── Sync History Table ──────────────────────────────────────────────────────

function SyncHistoryTable({ logs }: { logs: SyncLog[] }) {
  if (logs.length === 0) {
    return (
      <p className="py-3 text-center text-xs text-gray-500">
        No sync history yet
      </p>
    );
  }

  return (
    <div className="rounded-md border border-gray-100">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-gray-100 bg-gray-50 text-left font-medium uppercase tracking-wide text-gray-400">
            <th className="px-3 py-2">Date</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Found</th>
            <th className="px-3 py-2">Ingested</th>
            <th className="px-3 py-2">Skipped</th>
            <th className="px-3 py-2">Duration</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {logs.map((log) => (
            <tr key={log.id}>
              <td className="px-3 py-2 text-gray-700">
                {formatDateTime(log.started_at)}
              </td>
              <td className="px-3 py-2">
                <span
                  className={`inline-flex items-center gap-1 font-medium ${
                    log.status === "completed"
                      ? "text-green-700"
                      : log.status === "running"
                      ? "text-blue-700"
                      : "text-red-700"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      log.status === "completed"
                        ? "bg-green-500"
                        : log.status === "running"
                        ? "bg-blue-500"
                        : "bg-red-500"
                    }`}
                  />
                  {log.status}
                </span>
              </td>
              <td className="px-3 py-2 text-gray-600">{log.emails_found}</td>
              <td className="px-3 py-2 text-green-700">
                {log.emails_ingested}
              </td>
              <td className="px-3 py-2 text-gray-500">
                {log.emails_skipped}
              </td>
              <td className="px-3 py-2 text-gray-500">
                {log.completed_at && log.started_at
                  ? formatDuration(log.started_at, log.completed_at)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatRelative(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay < 7) return `${diffDay}d ago`;
  return d.toLocaleDateString();
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(start: string, end: string): string {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function GmailIcon({ small }: { small?: boolean } = {}) {
  const size = small ? "h-4 w-4" : "h-5 w-5";
  return (
    <svg className={`${size} shrink-0`} viewBox="0 0 24 24" fill="none">
      <path
        d="M20 18h-2V9.25L12 13 6 9.25V18H4V6h1.2l6.8 4.25L18.8 6H20v12z"
        fill="#EA4335"
      />
      <path
        d="M22 6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6z"
        fill="none"
        stroke="#EA4335"
        strokeWidth="1.5"
      />
    </svg>
  );
}

function SyncIcon() {
  return (
    <svg
      className="h-3.5 w-3.5 shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
      />
    </svg>
  );
}

function SparklesIcon() {
  return (
    <svg
      className="h-3.5 w-3.5 shrink-0"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z"
      />
    </svg>
  );
}

function Spinner() {
  return (
    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
  );
}

function XIcon() {
  return (
    <svg
      className="h-4 w-4"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6 18L18 6M6 6l12 12"
      />
    </svg>
  );
}
