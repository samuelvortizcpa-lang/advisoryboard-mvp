import type { ReactNode } from "react";
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
        <div className="ml-[200px] pt-[56px] min-h-screen bg-[#f5f7f9]">
          {children}
        </div>
      </OrgProvider>
    </AuthGuard>
  );
}
