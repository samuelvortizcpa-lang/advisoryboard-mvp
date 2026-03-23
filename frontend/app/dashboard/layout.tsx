import type { ReactNode } from "react";
import Link from "next/link";
import AuthGuard from "@/components/layout/AuthGuard";
import { OrgProvider } from "@/contexts/OrgContext";
import Sidebar from "@/components/layout/Sidebar";
import TopBar from "@/components/layout/TopBar";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <OrgProvider>
        {/* Fixed sidebar + fixed top bar */}
        <Sidebar />
        <TopBar />

        {/* Page content — offset for sidebar width and topbar height */}
        <div className="ml-56 pt-[56px] min-h-screen flex flex-col bg-white dark:bg-gray-950">
          <div className="flex-1 overflow-y-auto p-6 lg:p-8">{children}</div>
          <footer className="py-4 text-center text-xs text-gray-400">
            <Link href="/privacy" className="hover:text-gray-600">Privacy Policy</Link>
            <span className="mx-2">&middot;</span>
            <Link href="/terms" className="hover:text-gray-600">Terms of Service</Link>
            <span className="mx-2">&middot;</span>
            &copy; 2026 Callwen, Inc.
          </footer>
        </div>
      </OrgProvider>
    </AuthGuard>
  );
}
