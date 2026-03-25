"use client";

import { useAuth } from "@clerk/nextjs";
import { useState } from "react";

import type { ProfileFlags } from "@/lib/api";
import { createStrategiesApi } from "@/lib/api";

interface Props {
  clientId: string;
  initialFlags: ProfileFlags;
  onFlagsChange: (flags: ProfileFlags) => void;
}

const FLAG_CONFIG: { key: keyof ProfileFlags; label: string; icon: () => JSX.Element }[] = [
  { key: "has_business_entity", label: "Business Entity", icon: BuildingIcon },
  { key: "has_real_estate", label: "Real Estate", icon: HomeIcon },
  { key: "is_real_estate_professional", label: "RE Professional", icon: CrownIcon },
  { key: "has_high_income", label: "High Income", icon: TrendingUpIcon },
  { key: "has_estate_planning", label: "Estate Planning", icon: ShieldIcon },
  { key: "is_medical_professional", label: "Medical", icon: HeartIcon },
  { key: "has_retirement_plans", label: "Retirement Plans", icon: PiggyBankIcon },
  { key: "has_investments", label: "Investments", icon: BarChartIcon },
  { key: "has_employees", label: "Employees", icon: UsersIcon },
];

export default function ProfileFlagsRow({ clientId, initialFlags, onFlagsChange }: Props) {
  const { getToken } = useAuth();
  const [flags, setFlags] = useState<ProfileFlags>(initialFlags);
  const [saving, setSaving] = useState<string | null>(null);

  async function handleToggle(key: keyof ProfileFlags) {
    const prev = flags;
    const next = { ...flags, [key]: !flags[key] };
    setFlags(next);
    onFlagsChange(next);
    setSaving(key);

    try {
      await createStrategiesApi(getToken).updateFlags(clientId, { [key]: next[key] });
    } catch {
      // Revert on error
      setFlags(prev);
      onFlagsChange(prev);
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-gray-400">
        Client Profile
      </p>
      <div className="flex flex-wrap gap-2">
        {FLAG_CONFIG.map(({ key, label, icon: Icon }) => {
          const active = flags[key];
          const isSaving = saving === key;
          return (
            <button
              key={key}
              onClick={() => handleToggle(key)}
              disabled={isSaving}
              className={[
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                active
                  ? "bg-blue-600 text-white shadow-sm"
                  : "border border-gray-200 bg-white text-gray-500 hover:border-gray-300 hover:text-gray-700",
                isSaving ? "opacity-60" : "",
              ].join(" ")}
            >
              <Icon />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Icons (inline SVGs matching project style) ──────────────────────────────

function BuildingIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
    </svg>
  );
}

function HomeIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955a1.126 1.126 0 011.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
    </svg>
  );
}

function CrownIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 17l3-9 6 4 6-4 3 9H3zM12 3l-1.5 4.5M12 3l1.5 4.5" />
    </svg>
  );
}

function TrendingUpIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18L9 11.25l4.306 4.307a11.95 11.95 0 015.814-5.519l2.74-1.22m0 0l-5.94-2.281m5.94 2.28l-2.28 5.941" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
    </svg>
  );
}

function PiggyBankIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function BarChartIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
    </svg>
  );
}
