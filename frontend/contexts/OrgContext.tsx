"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useAuth } from "@clerk/nextjs";

import { Organization, createOrganizationsApi } from "@/lib/api";

// ─── Context shape ──────────────────────────────────────────────────────────

interface OrgContextValue {
  /** All orgs the user belongs to */
  orgs: Organization[];
  /** Currently active org (firm-first, personal fallback) */
  activeOrg: Organization | null;
  /** Switch the active org */
  setActiveOrg: (org: Organization) => void;
  /** True until the initial org list fetch completes */
  isLoading: boolean;
  /** Derived: activeOrg.role === "admin" */
  isAdmin: boolean;
  /** Derived: activeOrg.org_type === "personal" */
  isPersonalOrg: boolean;
  /** Refresh the org list from the server */
  refreshOrgs: () => Promise<void>;
}

const OrgContext = createContext<OrgContextValue>({
  orgs: [],
  activeOrg: null,
  setActiveOrg: () => {},
  isLoading: true,
  isAdmin: false,
  isPersonalOrg: true,
  refreshOrgs: async () => {},
});

// ─── Provider ───────────────────────────────────────────────────────────────

export function OrgProvider({ children }: { children: React.ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [activeOrg, setActiveOrgState] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchOrgs = useCallback(async () => {
    try {
      const list = await createOrganizationsApi(getToken).list();
      setOrgs(list);

      // Pick active org: prefer first firm org, fall back to first org
      setActiveOrgState((prev) => {
        // If user already picked one that still exists, keep it
        if (prev && list.some((o) => o.id === prev.id)) {
          // Update the cached copy (role/member_count may have changed)
          return list.find((o) => o.id === prev.id) ?? prev;
        }
        const firm = list.find((o) => o.org_type === "firm");
        return firm ?? list[0] ?? null;
      });
    } catch {
      // Non-fatal — user may not have any orgs yet
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (!isLoaded || !isSignedIn) return;
    fetchOrgs();
  }, [isLoaded, isSignedIn, fetchOrgs]);

  const setActiveOrg = useCallback((org: Organization) => {
    setActiveOrgState(org);
  }, []);

  const value = useMemo<OrgContextValue>(
    () => ({
      orgs,
      activeOrg,
      setActiveOrg,
      isLoading,
      isAdmin: activeOrg?.role === "admin",
      isPersonalOrg: activeOrg?.org_type === "personal",
      refreshOrgs: fetchOrgs,
    }),
    [orgs, activeOrg, setActiveOrg, isLoading, fetchOrgs]
  );

  return <OrgContext.Provider value={value}>{children}</OrgContext.Provider>;
}

// ─── Hook ───────────────────────────────────────────────────────────────────

export function useOrg() {
  return useContext(OrgContext);
}
