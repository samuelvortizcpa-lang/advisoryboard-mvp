"use client";

import { useMemo } from "react";
import { useAuth } from "@clerk/nextjs";
import { useOrg } from "@/contexts/OrgContext";

import {
  createClientsApi,
  createClientTypesApi,
  createRagApi,
  createUsageApi,
  createAdminApi,
  createStripeApi,
  createBriefsApi,
  createConsentApi,
  createAlertsApi,
  createActionItemsApi,
  createTimelineApi,
  createDocumentsApi,
  createIntegrationsApi,
  createOrganizationsApi,
  createContradictionsApi,
} from "@/lib/api";

/**
 * Returns pre-configured API instances scoped to the active org.
 * Pages can destructure just what they need:
 *
 *   const { clients, documents } = useApi();
 */
export function useApi() {
  const { getToken } = useAuth();
  const { activeOrg } = useOrg();
  const orgId = activeOrg?.id;

  return useMemo(
    () => ({
      clients: createClientsApi(getToken, orgId),
      clientTypes: createClientTypesApi(getToken, orgId),
      rag: createRagApi(getToken, orgId),
      usage: createUsageApi(getToken, orgId),
      admin: createAdminApi(getToken, orgId),
      stripe: createStripeApi(getToken, orgId),
      briefs: createBriefsApi(getToken, orgId),
      consents: createConsentApi(getToken, orgId),
      alerts: createAlertsApi(getToken, orgId),
      actionItems: createActionItemsApi(getToken, orgId),
      timeline: createTimelineApi(getToken, orgId),
      documents: createDocumentsApi(getToken, orgId),
      integrations: createIntegrationsApi(getToken, orgId),
      organizations: createOrganizationsApi(getToken, orgId),
      contradictions: createContradictionsApi(getToken, orgId),
    }),
    [getToken, orgId]
  );
}
