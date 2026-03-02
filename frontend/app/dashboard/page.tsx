import { auth, currentUser } from "@clerk/nextjs/server";
import { UserButton } from "@clerk/nextjs";
import Link from "next/link";
import { redirect } from "next/navigation";

async function fetchClientCount(token: string | null): Promise<number> {
  if (!token) return 0;
  try {
    const res = await fetch(
      "http://localhost:8000/api/clients?skip=0&limit=1",
      {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      }
    );
    if (!res.ok) return 0;
    const data = await res.json();
    return data.total ?? 0;
  } catch {
    return 0;
  }
}

export default async function DashboardPage() {
  const { userId, getToken } = await auth();

  if (!userId) {
    redirect("/sign-in");
  }

  const [user, token] = await Promise.all([currentUser(), getToken()]);

  const displayName =
    [user?.firstName, user?.lastName].filter(Boolean).join(" ") || "there";
  const email = user?.emailAddresses[0]?.emailAddress ?? "";
  const clientCount = await fetchClientCount(token);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top navigation */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <span className="text-lg font-semibold text-gray-900">
            AdvisoryBoard
          </span>
          <div className="flex items-center gap-5">
            <Link
              href="/dashboard/clients"
              className="text-sm font-medium text-gray-600 hover:text-gray-900 transition-colors"
            >
              Clients
            </Link>
            <UserButton afterSignOutUrl="/" />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Welcome card */}
        <div className="rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
          <p className="text-sm font-medium uppercase tracking-wide text-blue-600">
            Dashboard
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-gray-900">
            Welcome back, {displayName}
          </h1>
          {email && (
            <p className="mt-1 text-sm text-gray-500">{email}</p>
          )}

          <p className="mt-5 leading-relaxed text-gray-600">
            Manage your CPA client relationships, log interactions, and organise
            documents — all in one place.
          </p>

          {/* Stats */}
          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {/* Clients — live count, links to the list */}
            <Link
              href="/dashboard/clients"
              className="group rounded-lg border border-gray-100 bg-gray-50 px-5 py-4 transition-colors hover:border-blue-200 hover:bg-blue-50"
            >
              <p className="text-2xl font-semibold text-gray-900 transition-colors group-hover:text-blue-700">
                {clientCount}
              </p>
              <p className="mt-0.5 text-sm text-gray-500 transition-colors group-hover:text-blue-600">
                Clients →
              </p>
            </Link>

            <StatCard label="Interactions" value="—" />
            <StatCard label="Documents" value="—" />
          </div>
        </div>

        {/* Quick actions */}
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Quick Actions
          </h2>
          <div className="mt-4 flex flex-wrap gap-3">
            <Link
              href="/dashboard/clients/new"
              className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              + Add Client
            </Link>
            <Link
              href="/dashboard/clients"
              className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
            >
              View All Clients
            </Link>
          </div>
        </div>

        {/* Account details */}
        <div className="mt-6 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
            Account
          </h2>
          <dl className="mt-4 space-y-3">
            <Row label="Name" value={displayName} />
            <Row label="Email" value={email || "—"} />
            <Row label="User ID" value={userId} mono />
          </dl>
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 px-5 py-4">
      <p className="text-2xl font-semibold text-gray-900">{value}</p>
      <p className="mt-0.5 text-sm text-gray-500">{label}</p>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline gap-4 text-sm">
      <dt className="w-20 shrink-0 font-medium text-gray-500">{label}</dt>
      <dd className={`text-gray-900 ${mono ? "font-mono text-xs break-all" : ""}`}>
        {value}
      </dd>
    </div>
  );
}
