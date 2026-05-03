"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import type { ClientCadenceResponse, DeliverableKey } from "@/lib/api";
import { createCadenceApi } from "@/lib/api";
import ActiveCadenceCard from "./ActiveCadenceCard";
import AssignTemplateDrawer from "./AssignTemplateDrawer";
import DeliverableTogglesGrid from "./DeliverableTogglesGrid";
import EmptyCadenceState from "./EmptyCadenceState";

interface CadenceTabProps {
  clientId: string;
}

export default function CadenceTab({ clientId }: CadenceTabProps) {
  const { getToken } = useAuth();
  const { activeOrg, isAdmin: isOrgAdmin } = useOrg();
  const isFirmAdmin = activeOrg !== null && isOrgAdmin;

  const [cadence, setCadence] = useState<ClientCadenceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const api = useCallback(
    () => createCadenceApi(getToken, activeOrg?.id),
    [getToken, activeOrg?.id],
  );

  const fetchCadence = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api().getClientCadence(clientId);
      setCadence(data);
    } catch (err: unknown) {
      if ((err as { status?: number }).status === 404) {
        setCadence(null);
      } else {
        setError("Failed to load cadence. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }, [api, clientId]);

  useEffect(() => {
    fetchCadence();
  }, [fetchCadence]);

  async function handleAssign(templateId: string) {
    const data = await api().assignCadence(clientId, templateId);
    setCadence(data);
  }

  async function handleToggle(key: DeliverableKey, newValue: boolean) {
    if (!cadence) return;
    // Optimistic update
    const prev = cadence;
    const newOverrides = { ...cadence.overrides, [key]: newValue };
    const newEffective = { ...cadence.effective_flags, [key]: newValue };
    setCadence({ ...cadence, overrides: newOverrides, effective_flags: newEffective });

    try {
      const updated = await api().updateOverrides(clientId, { [key]: newValue });
      setCadence(updated);
    } catch {
      setCadence(prev);
    }
  }

  async function handleResetAll() {
    if (!cadence) return;
    setLoading(true);
    try {
      const updated = await api().assignCadence(clientId, cadence.template_id);
      setCadence(updated);
    } catch {
      setError("Failed to reset overrides. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  // Loading skeleton
  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-20 animate-pulse rounded-xl bg-gray-100" />
        <div className="h-64 animate-pulse rounded-xl bg-gray-100" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-sm text-red-700">{error}</p>
        <button
          onClick={fetchCadence}
          className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    );
  }

  // No cadence assigned
  if (!cadence) {
    return (
      <>
        <EmptyCadenceState isAdmin={isFirmAdmin} onPickClick={() => setDrawerOpen(true)} />
        <AssignTemplateDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          currentTemplateId={null}
          onAssign={handleAssign}
        />
      </>
    );
  }

  // Active cadence
  return (
    <div className="space-y-4">
      <ActiveCadenceCard
        cadence={cadence}
        isAdmin={isFirmAdmin}
        onChangeClick={() => setDrawerOpen(true)}
      />
      <DeliverableTogglesGrid
        effectiveFlags={cadence.effective_flags}
        overrides={cadence.overrides}
        isAdmin={isFirmAdmin}
        onToggle={handleToggle}
        onResetAll={handleResetAll}
      />
      <AssignTemplateDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        currentTemplateId={cadence.template_id}
        onAssign={handleAssign}
      />
    </div>
  );
}
