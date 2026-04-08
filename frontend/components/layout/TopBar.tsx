"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { UserButton } from "@clerk/nextjs";
import { createClientsApi } from "@/lib/api";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * If the current pathname is a client-detail route (/dashboard/clients/[id]),
 * returns the client ID string.  Returns null for /new and for all other routes.
 */
function extractClientId(pathname: string): string | null {
  const prefix = "/dashboard/clients/";
  if (!pathname.startsWith(prefix)) return null;
  const segment = pathname.slice(prefix.length).split("/")[0];
  // Exclude the /new route
  if (!segment || segment === "new") return null;
  return segment;
}

// ─── Breadcrumb logic ─────────────────────────────────────────────────────────

type Crumb = { label: string; href?: string };

function getBreadcrumbs(
  pathname: string,
  clientName: string | null
): Crumb[] {
  // /dashboard/clients/new
  if (pathname === "/dashboard/clients/new") {
    return [
      { label: "Clients", href: "/dashboard/clients" },
      { label: "New Client" },
    ];
  }
  // /dashboard/clients/[id]
  if (extractClientId(pathname)) {
    return [
      { label: "Clients", href: "/dashboard/clients" },
      // Show "…" while the name is loading, then the real name
      { label: clientName ?? "…" },
    ];
  }
  // /dashboard/clients
  if (pathname === "/dashboard/clients") {
    return [{ label: "Clients" }];
  }
  // /dashboard/actions
  if (pathname === "/dashboard/actions") {
    return [{ label: "Action Items" }];
  }
  // /dashboard/calendar
  if (pathname === "/dashboard/calendar") {
    return [{ label: "Calendar" }];
  }
  // /dashboard/practice-book
  if (pathname === "/dashboard/practice-book") {
    return [{ label: "Practice Book" }];
  }
  // /dashboard/strategy-dashboard
  if (pathname === "/dashboard/strategy-dashboard") {
    return [{ label: "Strategies" }];
  }
  // /dashboard/settings sub-pages
  if (pathname.startsWith("/dashboard/settings/")) {
    const sub = pathname.split("/dashboard/settings/")[1];
    const settingsLabels: Record<string, string> = {
      integrations: "Email Sync",
      engagements: "Engagements",
      extension: "Extension",
      usage: "Usage Analytics",
      organization: "Organization",
      subscriptions: "Subscriptions",
    };
    const label = settingsLabels[sub] || sub;
    return [
      { label: "Settings", href: "/dashboard/settings" },
      { label },
    ];
  }
  // /dashboard/settings
  if (pathname === "/dashboard/settings") {
    return [{ label: "Settings" }];
  }
  // /dashboard/strategies, /dashboard/engagements, /dashboard/email-sync, /dashboard/organization
  const topLevelLabels: Record<string, string> = {
    "/dashboard/strategies": "Strategies",
    "/dashboard/engagements": "Engagements",
    "/dashboard/email-sync": "Email Sync",
    "/dashboard/organization": "Organization",
  };
  if (topLevelLabels[pathname]) {
    return [{ label: topLevelLabels[pathname] }];
  }
  // /dashboard (and anything else)
  return [{ label: "Overview" }];
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function TopBar() {
  const pathname = usePathname();
  const { getToken } = useAuth();

  // Client name state — only populated when on a client-detail route
  const [clientName, setClientName] = useState<string | null>(null);

  const clientId = extractClientId(pathname);

  useEffect(() => {
    if (!clientId) {
      setClientName(null);
      return;
    }

    let cancelled = false;

    createClientsApi(getToken)
      .get(clientId)
      .then((c) => {
        if (!cancelled) setClientName(c.name);
      })
      .catch(() => {
        // Leave as null — the breadcrumb will show "…" gracefully
        if (!cancelled) setClientName(null);
      });

    return () => {
      cancelled = true;
    };
  }, [clientId, getToken]);

  const crumbs = getBreadcrumbs(pathname, clientName);

  return (
    <header className="fixed left-56 right-0 top-0 z-20 flex h-[56px] items-center justify-between border-b border-gray-200 bg-white px-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm" aria-label="breadcrumb">
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && (
              <span className="select-none text-gray-300" aria-hidden="true">
                /
              </span>
            )}
            {crumb.href ? (
              <Link
                href={crumb.href}
                className="text-gray-500 transition-colors hover:text-gray-800"
              >
                {crumb.label}
              </Link>
            ) : (
              <span
                className={`font-semibold ${
                  crumb.label === "…"
                    ? "text-gray-300"   // subtle loading indicator
                    : "text-gray-900"
                }`}
              >
                {crumb.label}
              </span>
            )}
          </span>
        ))}
      </nav>

      {/* Right: Clerk user menu */}
      <UserButton />
    </header>
  );
}
