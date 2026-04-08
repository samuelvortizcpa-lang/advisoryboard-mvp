import type { ReactNode } from "react";
import Link from "next/link";
import AuthGuard from "@/components/layout/AuthGuard";
import { OrgProvider } from "@/contexts/OrgContext";
import DashboardShell from "@/components/layout/DashboardShell";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <OrgProvider>
        <DashboardShell>
          <div className="flex-1 overflow-y-auto p-6 lg:p-8">{children}</div>
          <footer className="py-4 text-center text-xs text-gray-400">
            <Link href="/privacy" className="hover:text-gray-600">Privacy Policy</Link>
            <span className="mx-2">&middot;</span>
            <Link href="/terms" className="hover:text-gray-600">Terms of Service</Link>
            <span className="mx-2">&middot;</span>
            &copy; 2026 Callwen, Inc.
          </footer>
        </DashboardShell>
      </OrgProvider>
    </AuthGuard>
  );
}
