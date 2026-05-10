"use client";

import { useAuth } from "@clerk/nextjs";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  Client,
  IntegrationConnection,
  RoutingRule,
  SyncLog,
  ZoomRule,
  createClientsApi,
  createIntegrationsApi,
} from "@/lib/api";
import HelpTooltip from "@/components/ui/HelpTooltip";

// ─── Main page ────────────────────────────────────────────────────────────────

export default function IntegrationsSettingsPage() {
  const { getToken } = useAuth();
  const searchParams = useSearchParams();

  const [connections, setConnections] = useState<IntegrationConnection[]>([]);
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [zoomRules, setZoomRules] = useState<ZoomRule[]>([]);
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

  // ── Zoom rule form ──
  const [showAddZoomRule, setShowAddZoomRule] = useState(false);
  const [newZoomMatchField, setNewZoomMatchField] = useState("topic_contains");
  const [newZoomMatchValue, setNewZoomMatchValue] = useState("");
  const [newZoomClientId, setNewZoomClientId] = useState("");
  const [addingZoomRule, setAddingZoomRule] = useState(false);

  // ── Auto-generate state ──
  const [autoGenerating, setAutoGenerating] = useState(false);
  const [autoGeneratingZoom, setAutoGeneratingZoom] = useState(false);

  // ── History expand ──
  const [expandedHistoryId, setExpandedHistoryId] = useState<string | null>(
    null
  );

  // ── Connecting ──
  const [connectingGoogle, setConnectingGoogle] = useState(false);
  const [connectingMicrosoft, setConnectingMicrosoft] = useState(false);
  const [connectingZoom, setConnectingZoom] = useState(false);
  const [connectingFrontOAuth, setConnectingFrontOAuth] = useState(false);
  const [connectingFrontToken, setConnectingFrontToken] = useState(false);
  const [showFrontTokenInput, setShowFrontTokenInput] = useState(false);
  const [frontApiToken, setFrontApiToken] = useState("");

  // ── Fathom ──
  const [connectingFathom, setConnectingFathom] = useState(false);
  const [fathomApiKey, setFathomApiKey] = useState("");
  const [showFathomKeyInput, setShowFathomKeyInput] = useState(false);
  const [fathomApiWarning, setFathomApiWarning] = useState<string | null>(null);
  const [fathomImportFile, setFathomImportFile] = useState<File | null>(null);
  const [fathomImportClientId, setFathomImportClientId] = useState("");
  const [importingFathom, setImportingFathom] = useState(false);

  // ── Auto-sync status ──
  const [autoSyncStatus, setAutoSyncStatus] = useState<{
    scheduler_running: boolean;
    last_run_at: string | null;
    next_run_at: string | null;
    active_syncs: string[];
    last_run_summary: {
      connections_checked: number;
      connections_synced: number;
      connections_skipped: number;
      connections_failed: number;
    } | null;
  } | null>(null);

  // ── Activity feed ──
  const [activityFeed, setActivityFeed] = useState<SyncLog[]>([]);
  const [showActivityFeed, setShowActivityFeed] = useState(false);
  const activityIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadData = useCallback(async () => {
    try {
      const api = createIntegrationsApi(getToken);
      const clientsApi = createClientsApi(getToken);
      const [conns, rls, zRls, clientList] = await Promise.all([
        api.listConnections(),
        api.listRoutingRules(),
        api.listZoomRules(),
        clientsApi.list(0, 200),
      ]);
      setConnections(conns);
      setRules(rls);
      setZoomRules(zRls);
      setClients(clientList.items);
      setError(null);

      // Load auto-sync status (non-blocking — may fail if not admin)
      api.getAutoSyncStatus().then(setAutoSyncStatus).catch(() => {});
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Auto-refresh activity feed every 30 seconds
  const loadActivityFeed = useCallback(async () => {
    try {
      const api = createIntegrationsApi(getToken);
      const conns = connections.length > 0 ? connections : await api.listConnections();
      const allLogs: SyncLog[] = [];
      // Fetch last 5 logs per connection (in parallel)
      const results = await Promise.allSettled(
        conns.map((c) => api.getSyncHistory(c.id, 5))
      );
      results.forEach((r, i) => {
        if (r.status === "fulfilled") {
          r.value.forEach((log) => {
            // Tag each log with the provider for display
            (log as SyncLog & { _provider?: string })._provider = conns[i].provider;
            allLogs.push(log);
          });
        }
      });
      // Sort by started_at descending, take most recent 15
      allLogs.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
      setActivityFeed(allLogs.slice(0, 15));
    } catch {
      // Non-critical
    }
  }, [getToken, connections]);

  useEffect(() => {
    if (showActivityFeed) {
      loadActivityFeed();
      activityIntervalRef.current = setInterval(loadActivityFeed, 30_000);
    }
    return () => {
      if (activityIntervalRef.current) {
        clearInterval(activityIntervalRef.current);
        activityIntervalRef.current = null;
      }
    };
  }, [showActivityFeed, loadActivityFeed]);

  // Check for OAuth callback params
  useEffect(() => {
    if (searchParams.get("integration_connected") === "google") {
      setSuccessMsg("Gmail connected successfully! Set up routing rules below to start syncing emails.");
      loadData();
    }
    if (searchParams.get("connected") === "microsoft") {
      setSuccessMsg("Outlook connected successfully! Set up routing rules below to start syncing emails.");
      loadData();
    }
    if (searchParams.get("connected") === "zoom") {
      setSuccessMsg("Zoom connected successfully! Set up meeting rules below to start syncing recordings.");
      loadData();
    }
    if (searchParams.get("connected") === "front") {
      setSuccessMsg("Front connected successfully! Email routing rules will match conversations to clients.");
      loadData();
    }
    if (searchParams.get("integration_error")) {
      const err = searchParams.get("integration_error");
      if (err?.includes("front")) {
        setError("Failed to connect Front. Please try again.");
      } else if (err?.includes("zoom")) {
        setError("Failed to connect Zoom. Please try again.");
      } else if (err?.includes("microsoft")) {
        setError("Failed to connect Outlook. Please try again.");
      } else {
        setError("Failed to connect Gmail. Please try again.");
      }
    }
  }, [searchParams, loadData]);

  // ── Handlers ──

  const handleConnectGmail = async () => {
    setConnectingGoogle(true);
    try {
      const api = createIntegrationsApi(getToken);
      const { authorization_url } = await api.getGoogleAuthUrl();
      window.location.href = authorization_url;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to get auth URL");
      setConnectingGoogle(false);
    }
  };

  const handleConnectOutlook = async () => {
    setConnectingMicrosoft(true);
    try {
      const api = createIntegrationsApi(getToken);
      const { authorization_url } = await api.getMicrosoftAuthUrl();
      window.location.href = authorization_url;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to get auth URL");
      setConnectingMicrosoft(false);
    }
  };

  const handleConnectZoom = async () => {
    setConnectingZoom(true);
    try {
      const api = createIntegrationsApi(getToken);
      const { authorization_url } = await api.getZoomAuthUrl();
      window.location.href = authorization_url;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to get auth URL");
      setConnectingZoom(false);
    }
  };

  const handleConnectFrontOAuth = async () => {
    setConnectingFrontOAuth(true);
    try {
      const api = createIntegrationsApi(getToken);
      const { authorization_url } = await api.getFrontAuthUrl();
      window.location.href = authorization_url;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to get auth URL");
      setConnectingFrontOAuth(false);
    }
  };

  const handleConnectFrontToken = async () => {
    if (!frontApiToken.trim()) return;
    setConnectingFrontToken(true);
    try {
      const api = createIntegrationsApi(getToken);
      await api.connectFrontToken(frontApiToken.trim());
      setFrontApiToken("");
      setShowFrontTokenInput(false);
      setSuccessMsg("Front connected successfully via API token!");
      await loadData();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Invalid Front API token");
    } finally {
      setConnectingFrontToken(false);
    }
  };

  const handleConnectFathom = async () => {
    if (!fathomApiKey.trim()) return;
    setConnectingFathom(true);
    setFathomApiWarning(null);
    try {
      const api = createIntegrationsApi(getToken);
      await api.connectFathom(fathomApiKey.trim());
      setFathomApiKey("");
      setShowFathomKeyInput(false);
      setSuccessMsg("Fathom connected successfully!");
      await loadData();
    } catch (e: unknown) {
      setFathomApiWarning(e instanceof Error ? e.message : "Invalid Fathom API key");
    } finally {
      setConnectingFathom(false);
    }
  };

  const handleFathomImport = async () => {
    if (!fathomImportFile || !fathomImportClientId) return;
    setImportingFathom(true);
    try {
      const api = createIntegrationsApi(getToken);
      await api.importFathomTranscript(fathomImportFile, fathomImportClientId);
      setFathomImportFile(null);
      setFathomImportClientId("");
      setSuccessMsg("Fathom transcript imported successfully!");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to import transcript");
    } finally {
      setImportingFathom(false);
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

  const handleAddZoomRule = async () => {
    if (!newZoomMatchValue || !newZoomClientId) return;
    setAddingZoomRule(true);
    try {
      const api = createIntegrationsApi(getToken);
      const rule = await api.createZoomRule({
        match_field: newZoomMatchField,
        match_value: newZoomMatchValue,
        client_id: newZoomClientId,
      });
      setZoomRules((prev) => [...prev, rule]);
      setNewZoomMatchValue("");
      setNewZoomClientId("");
      setNewZoomMatchField("topic_contains");
      setShowAddZoomRule(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create Zoom rule");
    } finally {
      setAddingZoomRule(false);
    }
  };

  const handleDeleteZoomRule = async (ruleId: string) => {
    try {
      const api = createIntegrationsApi(getToken);
      await api.deleteZoomRule(ruleId);
      setZoomRules((prev) => prev.filter((r) => r.id !== ruleId));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete Zoom rule");
    }
  };

  const handleAutoGenerateZoomRules = async () => {
    setAutoGeneratingZoom(true);
    try {
      const api = createIntegrationsApi(getToken);
      const newRules = await api.autoGenerateZoomRules();
      if (newRules.length === 0) {
        setSuccessMsg("No new Zoom rules to generate. All client names already have matching rules.");
      } else {
        setZoomRules((prev) => [...prev, ...newRules]);
        setSuccessMsg(`Auto-generated ${newRules.length} Zoom rule${newRules.length > 1 ? "s" : ""} from client names.`);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to auto-generate Zoom rules");
    } finally {
      setAutoGeneratingZoom(false);
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
          Connect your accounts to auto-ingest emails, meetings, and
          conversations.
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

      {/* ───────── Auto-Sync Status ───────── */}
      {connections.length > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
          <div className="flex items-center gap-3">
            <span
              className={`h-2 w-2 rounded-full ${
                autoSyncStatus?.scheduler_running ? "bg-green-500" : "bg-gray-400"
              }`}
            />
            <span className="text-sm font-medium text-gray-700">
              Auto-sync:{" "}
              {autoSyncStatus?.scheduler_running ? (
                <span className="text-green-700">Active</span>
              ) : (
                <span className="text-gray-500">Inactive</span>
              )}
            </span>
            {autoSyncStatus?.scheduler_running && (
              <span className="text-xs text-gray-500">
                Runs every 15 minutes
              </span>
            )}
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            {autoSyncStatus?.last_run_at && (
              <span>
                Last run: {formatRelative(autoSyncStatus.last_run_at)}
              </span>
            )}
            {autoSyncStatus?.next_run_at && (
              <span>
                Next: {formatRelative(autoSyncStatus.next_run_at)}
              </span>
            )}
            {autoSyncStatus?.last_run_summary && (
              <span className="text-green-700">
                {autoSyncStatus.last_run_summary.connections_synced} synced
              </span>
            )}
          </div>
        </div>
      )}

      {/* ───────── Connected Accounts ───────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-900">
            Connected Accounts
          </h2>
        </div>

        <div className="p-6 space-y-6">
          {/* Active connection cards */}
          {connections.length > 0 && (
            <div className="space-y-4">
              {connections.map((conn) => {
                const isSyncing = syncingIds.has(conn.id);
                const result = syncResults[conn.id];
                const deepSyncTitle =
                  conn.provider === "zoom"
                    ? "Sync last 30 days (up to 100 recordings)"
                    : conn.provider === "front"
                    ? "Sync last 7 days (up to 200 conversations)"
                    : conn.provider === "fathom"
                    ? "Sync last 30 days (up to 100 meetings)"
                    : "Sync last 7 days (up to 200 emails)";
                const itemLabel =
                  conn.provider === "zoom"
                    ? "recordings"
                    : conn.provider === "front"
                    ? "conversations"
                    : conn.provider === "fathom"
                    ? "meetings"
                    : "emails";

                return (
                  <div
                    key={conn.id}
                    className="rounded-lg border border-gray-200 p-4"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <ProviderIconBubble provider={conn.provider} />
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-gray-900">
                              {conn.provider_email || providerLabel(conn.provider)}
                            </p>
                            <ProviderBadge provider={conn.provider} />
                          </div>
                          <p className="text-xs text-gray-500">
                            {conn.last_sync_at
                              ? `Last synced ${formatRelative(conn.last_sync_at)}`
                              : "Never synced"}
                            {conn.last_sync_at && autoSyncStatus?.scheduler_running && (
                              <span className="ml-1.5 inline-flex rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-medium text-green-700">
                                auto
                              </span>
                            )}
                          </p>
                        </div>
                      </div>

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
                          title={deepSyncTitle}
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
                            {result.status === "completed" ? "Completed" : "Failed"}
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
                          {(conn.provider === "zoom" || conn.provider === "front" || conn.provider === "fathom") && (
                            <span className="text-[10px] text-gray-400">({itemLabel})</span>
                          )}
                        </div>
                        {result.error_message && (
                          <p className="mt-1 text-xs text-red-600">
                            {result.error_message}
                          </p>
                        )}
                      </div>
                    )}

                    {expandedHistoryId === conn.id &&
                      syncHistories[conn.id] && (
                        <div className="mt-3">
                          <SyncHistoryTable
                            logs={syncHistories[conn.id]}
                            provider={conn.provider}
                          />
                        </div>
                      )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Provider connect grid */}
          <div className="grid grid-cols-2 gap-4">
            {/* Gmail */}
            <div className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <ProviderIconBubble provider="google" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">Gmail</p>
                  <p className="text-xs text-gray-500">Sync inbound client emails into the timeline. Outbound deliverables send via Callwen.</p>
                </div>
              </div>
              <button
                onClick={handleConnectGmail}
                disabled={connectingGoogle}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {connectingGoogle ? <Spinner /> : <GmailIcon small />}
                Connect Gmail
              </button>
            </div>

            {/* Outlook */}
            <div className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <ProviderIconBubble provider="microsoft" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">Outlook</p>
                  <p className="text-xs text-gray-500">Auto-import emails from Outlook/365</p>
                </div>
              </div>
              <button
                onClick={handleConnectOutlook}
                disabled={connectingMicrosoft}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border-2 border-[#0078d4] bg-white px-4 py-2 text-sm font-medium text-[#0078d4] transition-colors hover:bg-[#0078d4]/5 disabled:opacity-50"
              >
                {connectingMicrosoft ? <Spinner /> : <OutlookIcon small />}
                Connect Outlook
              </button>
            </div>

            {/* Zoom */}
            <div className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <ProviderIconBubble provider="zoom" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">Zoom</p>
                  <p className="text-xs text-gray-500">Auto-import meeting recordings and transcripts</p>
                </div>
              </div>
              <button
                onClick={handleConnectZoom}
                disabled={connectingZoom}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border-2 border-[#2D8CFF] bg-white px-4 py-2 text-sm font-medium text-[#2D8CFF] transition-colors hover:bg-[#2D8CFF]/5 disabled:opacity-50"
              >
                {connectingZoom ? <Spinner /> : <ZoomIcon small />}
                Connect Zoom
              </button>
            </div>

            {/* Front */}
            <div className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <ProviderIconBubble provider="front" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">Front</p>
                  <p className="text-xs text-gray-500">Auto-import conversations from Front shared inbox</p>
                </div>
              </div>
              {showFrontTokenInput ? (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="password"
                      value={frontApiToken}
                      onChange={(e) => setFrontApiToken(e.target.value)}
                      placeholder="Paste your Front API token..."
                      className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleConnectFrontToken}
                      disabled={connectingFrontToken || !frontApiToken.trim()}
                      className="inline-flex items-center gap-1.5 rounded-md bg-[#FF5C5C] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#e04e4e] disabled:opacity-50"
                    >
                      {connectingFrontToken ? <Spinner /> : "Connect"}
                    </button>
                  </div>
                  <button
                    onClick={() => { setShowFrontTokenInput(false); setFrontApiToken(""); }}
                    className="text-xs text-gray-500 hover:text-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleConnectFrontOAuth}
                      disabled={connectingFrontOAuth}
                      className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border-2 border-[#FF5C5C] bg-white px-4 py-2 text-sm font-medium text-[#FF5C5C] transition-colors hover:bg-[#FF5C5C]/5 disabled:opacity-50"
                    >
                      {connectingFrontOAuth ? <Spinner /> : <FrontIcon small />}
                      Connect with OAuth
                    </button>
                    <button
                      onClick={() => setShowFrontTokenInput(true)}
                      className="inline-flex items-center justify-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                    >
                      API Token
                    </button>
                  </div>
                  <p className="text-[10px] text-gray-400">
                    OAuth is recommended for team accounts. Use an API token for personal.
                  </p>
                </div>
              )}
            </div>

            {/* Fathom */}
            <div className="rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <ProviderIconBubble provider="fathom" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-gray-900">Fathom</p>
                  <p className="text-xs text-gray-500">Auto-import meeting notes and transcripts</p>
                </div>
              </div>
              {showFathomKeyInput ? (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center gap-2">
                    <input
                      type="password"
                      value={fathomApiKey}
                      onChange={(e) => { setFathomApiKey(e.target.value); setFathomApiWarning(null); }}
                      placeholder="Paste your Fathom API key..."
                      className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleConnectFathom}
                      disabled={connectingFathom || !fathomApiKey.trim()}
                      className="inline-flex items-center gap-1.5 rounded-md bg-[#7C3AED] px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-[#6D28D9] disabled:opacity-50"
                    >
                      {connectingFathom ? <Spinner /> : "Connect"}
                    </button>
                  </div>
                  {fathomApiWarning && (
                    <p className="text-xs text-red-600">{fathomApiWarning}</p>
                  )}
                  <button
                    onClick={() => { setShowFathomKeyInput(false); setFathomApiKey(""); setFathomApiWarning(null); }}
                    className="text-xs text-gray-500 hover:text-gray-700"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowFathomKeyInput(true)}
                  className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-md border-2 border-[#7C3AED] bg-white px-4 py-2 text-sm font-medium text-[#7C3AED] transition-colors hover:bg-[#7C3AED]/5 disabled:opacity-50"
                >
                  <FathomIcon small />
                  Connect with API Key
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ───────── Import Fathom Transcript ───────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="border-b border-gray-100 px-6 py-4">
          <h2 className="text-sm font-semibold text-gray-900">
            Import Fathom Transcript
          </h2>
          <p className="mt-0.5 text-xs text-gray-500">
            Upload a Fathom JSON transcript and assign it to a client
          </p>
        </div>
        <div className="p-6">
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Transcript File (.json)
              </label>
              <div
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  const file = e.dataTransfer.files?.[0];
                  if (file && file.name.endsWith(".json")) {
                    setFathomImportFile(file);
                  }
                }}
                className="relative"
              >
                <input
                  type="file"
                  accept=".json"
                  onChange={(e) => setFathomImportFile(e.target.files?.[0] ?? null)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-gray-100 file:px-2 file:py-1 file:text-xs file:font-medium file:text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
                {fathomImportFile && (
                  <p className="mt-1 text-xs text-gray-500">
                    Selected: {fathomImportFile.name} ({(fathomImportFile.size / 1024).toFixed(1)} KB)
                  </p>
                )}
              </div>
            </div>
            <div className="w-48">
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Client
              </label>
              <select
                value={fathomImportClientId}
                onChange={(e) => setFathomImportClientId(e.target.value)}
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
            <button
              onClick={handleFathomImport}
              disabled={importingFathom || !fathomImportFile || !fathomImportClientId}
              className="inline-flex items-center gap-1.5 rounded-md bg-[#7C3AED] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#6D28D9] disabled:opacity-50"
            >
              {importingFathom ? <Spinner /> : "Import"}
            </button>
          </div>
        </div>
      </section>

      {/* ───────── Email Routing Rules ───────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="flex items-center gap-1 text-sm font-semibold text-gray-900">
              Email Routing Rules
              <HelpTooltip content="Routing rules automatically match incoming emails to the right client based on sender or recipient email addresses." position="bottom" />
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

      {/* ───────── Zoom Meeting Rules ───────── */}
      <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">
              Zoom Meeting Rules
            </h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Map meeting topics, participant emails, or meeting IDs to clients
              for auto-routing recordings
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleAutoGenerateZoomRules}
              disabled={autoGeneratingZoom}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
            >
              {autoGeneratingZoom ? <Spinner /> : <SparklesIcon />}
              Auto-Generate
            </button>
            <button
              onClick={() => setShowAddZoomRule(!showAddZoomRule)}
              className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700"
            >
              + Add Rule
            </button>
          </div>
        </div>

        <div className="p-6">
          {/* Inline add form */}
          {showAddZoomRule && (
            <div className="mb-4 flex items-end gap-3 rounded-lg border border-blue-100 bg-blue-50/50 p-4">
              <div className="w-44">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Match Field
                </label>
                <select
                  value={newZoomMatchField}
                  onChange={(e) => setNewZoomMatchField(e.target.value)}
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="topic_contains">Topic Contains</option>
                  <option value="participant_email">Participant Email</option>
                  <option value="meeting_id_prefix">Meeting ID Prefix</option>
                </select>
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Match Value
                </label>
                <input
                  type="text"
                  value={newZoomMatchValue}
                  onChange={(e) => setNewZoomMatchValue(e.target.value)}
                  placeholder={
                    newZoomMatchField === "topic_contains"
                      ? "e.g. Weekly Standup"
                      : newZoomMatchField === "participant_email"
                      ? "e.g. client@example.com"
                      : "e.g. 123456"
                  }
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>
              <div className="w-48">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Client
                </label>
                <select
                  value={newZoomClientId}
                  onChange={(e) => setNewZoomClientId(e.target.value)}
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
              <button
                onClick={handleAddZoomRule}
                disabled={addingZoomRule || !newZoomMatchValue || !newZoomClientId}
                className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {addingZoomRule ? <Spinner /> : "Save"}
              </button>
              <button
                onClick={() => setShowAddZoomRule(false)}
                className="inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          )}

          {zoomRules.length === 0 && !showAddZoomRule ? (
            <div className="flex flex-col items-center rounded-lg border-2 border-dashed border-gray-200 px-6 py-8">
              <p className="text-sm text-gray-500">No Zoom meeting rules yet</p>
              <p className="mt-1 text-xs text-gray-400">
                Add rules to route recordings to clients, or auto-generate from
                client names
              </p>
            </div>
          ) : (
            zoomRules.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100 text-left text-xs font-medium uppercase tracking-wide text-gray-400">
                    <th className="pb-2 pr-4">Match Field</th>
                    <th className="pb-2 pr-4">Match Value</th>
                    <th className="pb-2 pr-4">Client</th>
                    <th className="pb-2 pr-4">Status</th>
                    <th className="pb-2 w-16"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {zoomRules.map((rule) => (
                    <tr key={rule.id} className="group">
                      <td className="py-2.5 pr-4">
                        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                          {rule.match_field === "topic_contains"
                            ? "Topic Contains"
                            : rule.match_field === "participant_email"
                            ? "Participant Email"
                            : "Meeting ID Prefix"}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 font-mono text-xs text-gray-900">
                        {rule.match_value}
                      </td>
                      <td className="py-2.5 pr-4 text-gray-700">
                        {rule.client_name}
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
                          onClick={() => handleDeleteZoomRule(rule.id)}
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

      {/* ───────── Sync Activity Feed ───────── */}
      {connections.length > 0 && (
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">
                Sync Activity
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">
                Recent sync activity across all connected providers
                {showActivityFeed && (
                  <span className="ml-1 text-gray-400">(auto-refreshes every 30s)</span>
                )}
              </p>
            </div>
            <button
              onClick={() => setShowActivityFeed(!showActivityFeed)}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              {showActivityFeed ? "Hide" : "Show"}
            </button>
          </div>

          {showActivityFeed && (
            <div className="p-6">
              {activityFeed.length === 0 ? (
                <p className="py-3 text-center text-xs text-gray-500">
                  No sync activity yet
                </p>
              ) : (
                <div className="space-y-2">
                  {activityFeed.map((log) => {
                    const logProvider = (log as SyncLog & { _provider?: string })._provider || "google";
                    return (
                      <div
                        key={log.id}
                        className="flex items-center justify-between rounded-md border border-gray-100 px-3 py-2"
                      >
                        <div className="flex items-center gap-2.5">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              log.status === "completed"
                                ? "bg-green-500"
                                : log.status === "running"
                                ? "bg-blue-500"
                                : "bg-red-500"
                            }`}
                          />
                          <ProviderBadge provider={logProvider} />
                          <span
                            className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                              log.sync_type === "scheduled"
                                ? "bg-blue-50 text-blue-600"
                                : "bg-gray-100 text-gray-600"
                            }`}
                          >
                            {log.sync_type === "scheduled" ? "auto" : "manual"}
                          </span>
                          <span className="text-xs text-gray-600">
                            {log.emails_found} found, {log.emails_ingested} ingested
                          </span>
                          {log.error_message && (
                            <span className="text-xs text-red-500 truncate max-w-[200px]">
                              {log.error_message}
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-gray-400">
                          {formatRelative(log.started_at)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

// ─── Sync History Table ──────────────────────────────────────────────────────

function SyncHistoryTable({ logs, provider }: { logs: SyncLog[]; provider: string }) {
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
            <th className="px-3 py-2">Provider</th>
            <th className="px-3 py-2">Type</th>
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
                <ProviderBadge provider={provider} />
              </td>
              <td className="px-3 py-2">
                <span
                  className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                    log.sync_type === "scheduled"
                      ? "bg-blue-50 text-blue-600"
                      : "bg-gray-100 text-gray-600"
                  }`}
                >
                  {log.sync_type === "scheduled" ? "auto" : "manual"}
                </span>
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

function OutlookIcon({ small }: { small?: boolean } = {}) {
  const size = small ? "h-4 w-4" : "h-5 w-5";
  return (
    <svg className={`${size} shrink-0`} viewBox="0 0 24 24" fill="none">
      <rect x="2" y="4" width="20" height="16" rx="2" stroke="#0078d4" strokeWidth="1.5" fill="none" />
      <path d="M2 8l10 5 10-5" stroke="#0078d4" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2 8l10 5 10-5V6a2 2 0 00-2-2H4a2 2 0 00-2 2v2z" fill="#0078d4" opacity="0.15" />
    </svg>
  );
}

function ZoomIcon({ small }: { small?: boolean } = {}) {
  const size = small ? "h-4 w-4" : "h-5 w-5";
  return (
    <svg className={`${size} shrink-0`} viewBox="0 0 24 24" fill="none">
      <rect x="2" y="5" width="20" height="14" rx="3" fill="#2D8CFF" opacity="0.15" stroke="#2D8CFF" strokeWidth="1.5" />
      <path d="M16 10l4-2v8l-4-2" stroke="#2D8CFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="4" y="8" width="10" height="8" rx="1.5" stroke="#2D8CFF" strokeWidth="1.5" fill="none" />
    </svg>
  );
}

function ProviderBadge({ provider }: { provider: string }) {
  const config =
    provider === "fathom"
      ? { bg: "bg-purple-50", text: "text-purple-700", label: "Fathom" }
      : provider === "front"
      ? { bg: "bg-red-50", text: "text-red-600", label: "Front" }
      : provider === "zoom"
      ? { bg: "bg-sky-100", text: "text-sky-700", label: "Zoom" }
      : provider === "microsoft"
      ? { bg: "bg-blue-100", text: "text-blue-700", label: "Outlook" }
      : { bg: "bg-red-100", text: "text-red-700", label: "Gmail" };
  return (
    <span
      className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${config.bg} ${config.text}`}
    >
      {config.label}
    </span>
  );
}

function providerLabel(provider: string): string {
  if (provider === "fathom") return "Fathom";
  if (provider === "front") return "Front";
  if (provider === "zoom") return "Zoom";
  if (provider === "microsoft") return "Outlook";
  return "Gmail";
}

function ProviderIconBubble({ provider }: { provider: string }) {
  const bg =
    provider === "fathom"
      ? "bg-purple-50"
      : provider === "front"
      ? "bg-red-50"
      : provider === "zoom"
      ? "bg-blue-50"
      : provider === "microsoft"
      ? "bg-blue-50"
      : "bg-red-50";
  return (
    <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${bg}`}>
      {provider === "fathom" ? (
        <FathomIcon />
      ) : provider === "front" ? (
        <FrontIcon />
      ) : provider === "zoom" ? (
        <ZoomIcon />
      ) : provider === "microsoft" ? (
        <OutlookIcon />
      ) : (
        <GmailIcon />
      )}
    </div>
  );
}

function FrontIcon({ small }: { small?: boolean } = {}) {
  const size = small ? "h-4 w-4" : "h-5 w-5";
  return (
    <svg className={`${size} shrink-0`} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="#FF5C5C" strokeWidth="1.5" fill="none" />
      <path d="M3 8h18" stroke="#FF5C5C" strokeWidth="1.5" />
      <path d="M7 12h6" stroke="#FF5C5C" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7 15.5h4" stroke="#FF5C5C" strokeWidth="1.5" strokeLinecap="round" />
      <rect x="3" y="4" width="18" height="4" rx="2" fill="#FF5C5C" opacity="0.15" />
    </svg>
  );
}

function FathomIcon({ small }: { small?: boolean } = {}) {
  const size = small ? "h-4 w-4" : "h-5 w-5";
  return (
    <svg className={`${size} shrink-0`} viewBox="0 0 24 24" fill="none">
      <path
        d="M12 2C8.13 2 5 5.13 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.87-3.13-7-7-7z"
        stroke="#7C3AED"
        strokeWidth="1.5"
        fill="#7C3AED"
        opacity="0.15"
      />
      <path
        d="M12 2C8.13 2 5 5.13 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.87-3.13-7-7-7z"
        stroke="#7C3AED"
        strokeWidth="1.5"
        fill="none"
      />
      <path d="M9 21h6" stroke="#7C3AED" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M10 19v2M14 19v2" stroke="#7C3AED" strokeWidth="1.5" strokeLinecap="round" />
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
