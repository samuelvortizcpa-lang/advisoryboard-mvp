import { auth, currentUser } from "@clerk/nextjs/server";
import { UserButton } from "@clerk/nextjs";
import { redirect } from "next/navigation";

export default async function DashboardPage() {
  const { userId } = await auth();

  if (!userId) {
    redirect("/sign-in");
  }

  const user = await currentUser();

  const displayName =
    [user?.firstName, user?.lastName].filter(Boolean).join(" ") || "there";
  const email = user?.emailAddresses[0]?.emailAddress ?? "";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top navigation */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <span className="text-lg font-semibold text-gray-900">
            AdvisoryBoard
          </span>
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Welcome card */}
        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-sm">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-blue-600 uppercase tracking-wide">
                Dashboard
              </p>
              <h1 className="mt-1 text-2xl font-semibold text-gray-900">
                Welcome back, {displayName}
              </h1>
              {email && (
                <p className="mt-1 text-sm text-gray-500">{email}</p>
              )}
            </div>
          </div>

          <p className="mt-6 text-gray-600 leading-relaxed">
            Your advisory board is ready. Add advisors, start conversations, and
            get strategic guidance tailored to your goals.
          </p>

          <div className="mt-8 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard label="Advisors" value="0" />
            <StatCard label="Sessions" value="0" />
            <StatCard label="Insights" value="0" />
          </div>
        </div>

        {/* Account details card */}
        <div className="mt-6 bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
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
    <div className="rounded-lg bg-gray-50 border border-gray-100 px-5 py-4">
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
      <dd
        className={`text-gray-900 ${mono ? "font-mono text-xs break-all" : ""}`}
      >
        {value}
      </dd>
    </div>
  );
}
