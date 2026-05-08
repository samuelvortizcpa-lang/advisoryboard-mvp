"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, useState } from "react";

import { useOrg } from "@/contexts/OrgContext";
import { createCadenceApi } from "@/lib/api";
import KickoffMemoDraftModal from "./KickoffMemoDraftModal";

interface DraftKickoffMemoButtonProps {
  clientId: string;
  clientName: string;
  clientEmail: string | null;
}

export default function DraftKickoffMemoButton({
  clientId,
  clientName,
  clientEmail,
}: DraftKickoffMemoButtonProps) {
  const { getToken } = useAuth();
  const { activeOrg, isAdmin: isOrgAdmin } = useOrg();
  const isFirmAdmin = activeOrg !== null && isOrgAdmin;

  const [enabledDeliverables, setEnabledDeliverables] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);

  // Load enabled deliverables (cadence gate) — mirrors SendEmailModal.tsx:272-287
  useEffect(() => {
    let mounted = true;
    createCadenceApi(getToken)
      .getEnabledDeliverables(clientId)
      .then((res) => {
        if (mounted) setEnabledDeliverables(res.enabled);
      })
      .catch(() => {
        // Fail-safe: leave enabledDeliverables empty; button stays hidden
      });
    return () => {
      mounted = false;
    };
  }, [clientId, getToken]);

  if (!isFirmAdmin || !enabledDeliverables.includes("kickoff_memo")) return null;

  return (
    <>
      <button
        onClick={() => setModalOpen(true)}
        className="inline-flex items-center gap-2 rounded-md bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
        Draft Kickoff
      </button>
      <KickoffMemoDraftModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        clientId={clientId}
        clientName={clientName}
        clientEmail={clientEmail}
      />
    </>
  );
}
