"use client";

import Link from "next/link";

const settingsCards = [
  {
    title: "Integrations / Email Sync",
    description: "Connect email accounts and configure routing rules",
    href: "/dashboard/settings/integrations",
  },
];

export default function SettingsPage() {
  return (
    <div className="px-8 py-8 space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">
          Configuration
        </p>
        <h1 className="mt-1 text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your workspace preferences and integrations
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {settingsCards.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="group rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-colors hover:border-blue-200 hover:bg-blue-50"
          >
            <h2 className="text-base font-semibold text-gray-900 transition-colors group-hover:text-blue-700">
              {card.title}
            </h2>
            <p className="mt-1 text-sm text-gray-500 transition-colors group-hover:text-blue-600">
              {card.description}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
