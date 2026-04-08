"use client";

import { useState, useCallback } from "react";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

/**
 * Client-side shell that manages mobile sidebar open/close state
 * and wires the hamburger button in TopBar to the Sidebar overlay.
 */
export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const pathname = usePathname();

  // Close sidebar on navigation
  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  const handleOpen = useCallback(() => setSidebarOpen(true), []);
  const handleClose = useCallback(() => setSidebarOpen(false), []);

  return (
    <>
      {/* Backdrop — mobile only, visible when sidebar is open */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={handleClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <Sidebar mobileOpen={sidebarOpen} onClose={handleClose} />

      {/* Top bar with hamburger on mobile */}
      <TopBar onMenuClick={handleOpen} />

      {/* Page content — offset for sidebar on md+, full-width on mobile */}
      <div className="md:ml-56 pt-[56px] min-h-screen flex flex-col bg-white dark:bg-gray-950">
        {children}
      </div>
    </>
  );
}
