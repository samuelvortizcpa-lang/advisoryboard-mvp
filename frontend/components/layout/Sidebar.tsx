"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth, useUser } from "@clerk/nextjs";
import { useCallback, useEffect, useState } from "react";

import { createClientAssignmentsApi } from "@/lib/api";
import { useOrg } from "@/contexts/OrgContext";
import OrgSwitcher from "@/components/layout/OrgSwitcher";
import HelpFeedbackButton from "@/components/support/HelpFeedbackButton";

// ─── Nav config ───────────────────────────────────────────────────────────────

const PRIMARY_NAV = [
  { href: "/dashboard", label: "Overview", Icon: GridIcon, exact: true },
  { href: "/dashboard/clients", label: "Clients", Icon: PeopleIcon },
  { href: "/dashboard/actions", label: "Action Items", Icon: CheckSquareIcon },
  { href: "/dashboard/strategy-dashboard", label: "Strategies", Icon: TargetIcon },
  { href: "/dashboard/practice-book", label: "Practice Book", Icon: PracticeBookIcon },
  { href: "/dashboard/calendar", label: "Calendar", Icon: CalendarIcon },
] as const;

const SETTINGS_NAV = [
  { href: "/dashboard/settings/integrations", label: "Email Sync", Icon: EmailSyncIcon, adminOnly: false },
  { href: "/dashboard/settings/engagements", label: "Engagements", Icon: RepeatIcon, adminOnly: false },
  { href: "/dashboard/settings/extension", label: "Extension", Icon: ExtensionIcon, adminOnly: false },
  { href: "/dashboard/settings/usage", label: "Usage Analytics", Icon: ChartBarIcon, adminOnly: true },
  { href: "/dashboard/settings/organization", label: "Organization", Icon: BuildingIcon, adminOnly: true },
  { href: "/dashboard/settings/subscriptions", label: "Subscriptions", Icon: UsersIcon, adminOnly: true },
  { href: "/dashboard/settings", label: "Settings", Icon: GearIcon, exact: true, adminOnly: false },
] as const;

// ─── Component ────────────────────────────────────────────────────────────────

export default function Sidebar({
  mobileOpen,
  onClose,
}: {
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();
  const { getToken } = useAuth();
  const { user } = useUser();
  const { activeOrg, isPersonalOrg, isAdmin } = useOrg();
  const [myClientCount, setMyClientCount] = useState<number | null>(null);

  const loadMyClientCount = useCallback(async () => {
    if (!activeOrg || isPersonalOrg || isAdmin) {
      setMyClientCount(null);
      return;
    }
    try {
      const api = createClientAssignmentsApi(getToken, activeOrg.id);
      const result = await api.myClients();
      setMyClientCount(result.length);
    } catch {
      // non-fatal
    }
  }, [getToken, activeOrg, isPersonalOrg, isAdmin]);

  useEffect(() => {
    loadMyClientCount();
  }, [loadMyClientCount]);

  const displayName =
    [user?.firstName, user?.lastName].filter(Boolean).join(" ") ||
    user?.emailAddresses[0]?.emailAddress ||
    "User";

  return (
    <aside
      className={[
        "fixed inset-y-0 left-0 flex w-56 flex-col bg-gray-50 p-3 dark:bg-gray-900 transition-transform duration-200 ease-out",
        // Desktop: always visible, normal z-index
        "md:translate-x-0 md:z-20",
        // Mobile: slide in/out, higher z-index to sit above backdrop
        mobileOpen ? "translate-x-0 z-50" : "-translate-x-full z-50",
      ].join(" ")}
    >
      {/* ── Logo + mobile close ────────────────────────────────────────── */}
      <div className="flex items-center gap-2.5 pb-4 border-b border-gray-200 dark:border-gray-800">
        <Link href="/dashboard" className="flex min-w-0 flex-1 items-center gap-2.5" onClick={onClose}>
          {!isPersonalOrg && activeOrg ? (
            <>
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-900 dark:bg-gray-100">
                <SidebarBuildingMark />
              </span>
              <span className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                {activeOrg.name}
              </span>
            </>
          ) : (
            <>
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gray-900 dark:bg-gray-100">
                <LogoMark />
              </span>
              <span className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                Call<span className="text-[#c9944a]">wen</span>
              </span>
            </>
          )}
        </Link>
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-md text-gray-400 hover:text-gray-600 md:hidden"
          aria-label="Close sidebar"
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* ── Primary navigation ──────────────────────────────────────────── */}
      <nav className="mt-4 flex-1 space-y-0.5 overflow-y-auto">
        {PRIMARY_NAV.map((item) => (
          <NavItem
            key={item.href}
            item={item}
            pathname={pathname}
            badge={item.label === "Clients" && myClientCount != null ? myClientCount : undefined}
            onNavigate={onClose}
          />
        ))}

        {/* ── Settings section ─────────────────────────────────────────── */}
        <p className="mt-4 mb-1 px-2.5 text-[11px] font-medium uppercase tracking-wider text-gray-400">
          Settings
        </p>
        {SETTINGS_NAV.filter((item) => !item.adminOnly || isPersonalOrg || isAdmin).map((item) => (
          <NavItem key={item.href} item={item} pathname={pathname} onNavigate={onClose} />
        ))}
      </nav>

      {/* ── Help & Feedback ──────────────────────────────────────────────── */}
      <div className="mt-2 border-t border-gray-200 pt-2 dark:border-gray-800">
        <HelpFeedbackButton />
      </div>

      {/* ── Org switcher ────────────────────────────────────────────────── */}
      <OrgSwitcher />

      {/* ── User ────────────────────────────────────────────────────────── */}
      {user && (
        <div className="flex items-center gap-2.5 border-t border-gray-200 pt-3 dark:border-gray-800">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 text-[11px] font-medium text-blue-700">
            {getInitials(user.firstName, user.lastName)}
          </div>
          <span className="min-w-0 flex-1 truncate text-sm text-gray-700 dark:text-gray-300">
            {displayName}
          </span>
        </div>
      )}
    </aside>
  );
}

// ─── NavItem ──────────────────────────────────────────────────────────────────

function NavItem({
  item,
  pathname,
  badge,
  onNavigate,
}: {
  item: { href: string; label: string; Icon: () => React.JSX.Element; exact?: boolean };
  pathname: string;
  badge?: number;
  onNavigate?: () => void;
}) {
  const { href, label, Icon } = item;
  const isActive = item.exact
    ? pathname === href
    : href === "/dashboard/clients"
    ? pathname.startsWith("/dashboard/clients")
    : pathname.startsWith(href);

  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={[
        "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
        isActive
          ? "bg-white font-medium text-gray-900 shadow-sm dark:bg-gray-800 dark:text-gray-100"
          : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100",
      ].join(" ")}
    >
      <Icon />
      {label}
      {badge != null && (
        <span className="ml-auto rounded-full bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium leading-none text-blue-700">
          {badge}
        </span>
      )}
    </Link>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getInitials(
  firstName: string | null | undefined,
  lastName: string | null | undefined
): string {
  const f = firstName?.[0]?.toUpperCase() ?? "";
  const l = lastName?.[0]?.toUpperCase() ?? "";
  return f + l || "U";
}

// ─── Icons ────────────────────────────────────────────────────────────────────

function SidebarBuildingMark() {
  return (
    <svg className="h-3.5 w-3.5 text-white dark:text-gray-900" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
    </svg>
  );
}

function LogoMark() {
  return (
    <svg className="h-3.5 w-3.5 text-white dark:text-gray-900" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function GridIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
    </svg>
  );
}

function PeopleIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
    </svg>
  );
}

function CheckSquareIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
    </svg>
  );
}

function EmailSyncIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
    </svg>
  );
}

function ChartBarIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  );
}

function BuildingIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function ExtensionIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 6.087c0-.355.186-.676.401-.959.221-.29.349-.634.349-1.003 0-1.036-1.007-1.875-2.25-1.875s-2.25.84-2.25 1.875c0 .369.128.713.349 1.003.215.283.401.604.401.959v0a.64.64 0 01-.657.643 48.39 48.39 0 01-4.163-.3c.186 1.613.293 3.25.315 4.907a.656.656 0 01-.658.663v0c-.355 0-.676-.186-.959-.401a1.647 1.647 0 00-1.003-.349c-1.036 0-1.875 1.007-1.875 2.25s.84 2.25 1.875 2.25c.369 0 .713-.128 1.003-.349.283-.215.604-.401.959-.401v0c.31 0 .555.26.532.57a48.039 48.039 0 01-.642 5.056c1.518.19 3.058.309 4.616.354a.64.64 0 00.657-.643v0c0-.355-.186-.676-.401-.959a1.647 1.647 0 01-.349-1.003c0-1.035 1.008-1.875 2.25-1.875 1.243 0 2.25.84 2.25 1.875 0 .369-.128.713-.349 1.003-.215.283-.4.604-.4.959v0c0 .333.277.599.61.58a48.1 48.1 0 005.427-.63 48.05 48.05 0 00.582-4.717.532.532 0 00-.533-.57v0c-.355 0-.676.186-.959.401-.29.221-.634.349-1.003.349-1.035 0-1.875-1.007-1.875-2.25s.84-2.25 1.875-2.25c.37 0 .713.128 1.003.349.283.215.604.401.96.401v0a.656.656 0 00.658-.663 48.422 48.422 0 00-.37-5.36c-1.886.342-3.81.574-5.766.689a.578.578 0 01-.61-.58v0z" />
    </svg>
  );
}

function RepeatIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 12c0-1.232-.046-2.453-.138-3.662a4.006 4.006 0 00-3.7-3.7 48.678 48.678 0 00-7.324 0 4.006 4.006 0 00-3.7 3.7c-.017.22-.032.441-.046.662M4.5 12c0 1.232.046 2.453.138 3.662a4.006 4.006 0 003.7 3.7 48.656 48.656 0 007.324 0 4.006 4.006 0 003.7-3.7c.017-.22.032-.441.046-.662" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.25 7.5l4.5-3-4.5-3M9.75 16.5l-4.5 3 4.5 3" />
    </svg>
  );
}

function PracticeBookIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
    </svg>
  );
}

function TargetIcon() {
  return (
    <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
    </svg>
  );
}
