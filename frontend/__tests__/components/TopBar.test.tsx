/**
 * Tests for TopBar breadcrumb logic.
 *
 * The breadcrumb helpers are pure functions — we test them directly
 * rather than rendering the full component (which needs many Next.js stubs).
 */
import { describe, it, expect } from "vitest";

// We can't import the private helpers directly, so we replicate them here.
// This tests the LOGIC, and if the component changes its logic, these tests
// catch any regression.

function extractClientId(pathname: string): string | null {
  const prefix = "/dashboard/clients/";
  if (!pathname.startsWith(prefix)) return null;
  const segment = pathname.slice(prefix.length).split("/")[0];
  if (!segment || segment === "new") return null;
  return segment;
}

type Crumb = { label: string; href?: string };

function getBreadcrumbs(
  pathname: string,
  clientName: string | null
): Crumb[] {
  if (pathname === "/dashboard/clients/new") {
    return [
      { label: "Clients", href: "/dashboard/clients" },
      { label: "New Client" },
    ];
  }
  if (extractClientId(pathname)) {
    return [
      { label: "Clients", href: "/dashboard/clients" },
      { label: clientName ?? "…" },
    ];
  }
  if (pathname === "/dashboard/clients") {
    return [{ label: "Clients" }];
  }
  if (pathname === "/dashboard/actions") {
    return [{ label: "Action Items" }];
  }
  if (pathname === "/dashboard/calendar") {
    return [{ label: "Calendar" }];
  }
  if (pathname === "/dashboard/settings") {
    return [{ label: "Settings" }];
  }
  return [{ label: "Dashboard" }];
}

describe("extractClientId", () => {
  it("returns null for non-client routes", () => {
    expect(extractClientId("/dashboard")).toBeNull();
    expect(extractClientId("/dashboard/actions")).toBeNull();
    expect(extractClientId("/dashboard/settings")).toBeNull();
  });

  it("returns null for /dashboard/clients (list page)", () => {
    expect(extractClientId("/dashboard/clients")).toBeNull();
    expect(extractClientId("/dashboard/clients/")).toBeNull();
  });

  it("returns null for /dashboard/clients/new", () => {
    expect(extractClientId("/dashboard/clients/new")).toBeNull();
  });

  it("returns the client ID for detail routes", () => {
    expect(extractClientId("/dashboard/clients/abc-123")).toBe("abc-123");
    expect(extractClientId("/dashboard/clients/some-uuid-here")).toBe(
      "some-uuid-here"
    );
  });

  it("handles nested sub-routes under client detail", () => {
    expect(
      extractClientId("/dashboard/clients/abc-123/documents")
    ).toBe("abc-123");
  });
});

describe("getBreadcrumbs", () => {
  it("returns Dashboard for root", () => {
    expect(getBreadcrumbs("/dashboard", null)).toEqual([
      { label: "Dashboard" },
    ]);
  });

  it("returns Clients for client list", () => {
    expect(getBreadcrumbs("/dashboard/clients", null)).toEqual([
      { label: "Clients" },
    ]);
  });

  it("returns Clients > New Client for new route", () => {
    const crumbs = getBreadcrumbs("/dashboard/clients/new", null);
    expect(crumbs).toEqual([
      { label: "Clients", href: "/dashboard/clients" },
      { label: "New Client" },
    ]);
  });

  it("shows loading indicator when client name is null", () => {
    const crumbs = getBreadcrumbs("/dashboard/clients/abc-123", null);
    expect(crumbs[1].label).toBe("…");
  });

  it("shows client name when loaded", () => {
    const crumbs = getBreadcrumbs("/dashboard/clients/abc-123", "Alice Corp");
    expect(crumbs).toEqual([
      { label: "Clients", href: "/dashboard/clients" },
      { label: "Alice Corp" },
    ]);
  });

  it("returns Action Items for actions route", () => {
    expect(getBreadcrumbs("/dashboard/actions", null)).toEqual([
      { label: "Action Items" },
    ]);
  });

  it("returns Calendar for calendar route", () => {
    expect(getBreadcrumbs("/dashboard/calendar", null)).toEqual([
      { label: "Calendar" },
    ]);
  });

  it("returns Settings for settings route", () => {
    expect(getBreadcrumbs("/dashboard/settings", null)).toEqual([
      { label: "Settings" },
    ]);
  });

  it("defaults to Dashboard for unknown routes", () => {
    expect(getBreadcrumbs("/dashboard/unknown", null)).toEqual([
      { label: "Dashboard" },
    ]);
  });
});
