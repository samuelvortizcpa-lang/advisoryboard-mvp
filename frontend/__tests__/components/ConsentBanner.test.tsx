/**
 * Tests for ConsentBanner helper functions and consent status display logic.
 *
 * These test the pure helper functions from ConsentBanner which handle
 * date formatting, validation, and consent status state transitions.
 */
import { describe, it, expect } from "vitest";

// ─── Helper functions replicated from ConsentBanner.tsx ─────────────────────

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "\u2014";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}

function oneYearFromISO(dateStr: string): string {
  const d = new Date(dateStr);
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
}

function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const diff = Date.now() - new Date(iso).getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

// Consent statuses that should show "blocked" state in the UI
const AI_ALLOWED_STATUSES = new Set([
  "obtained",
  "acknowledged",
  "not_required",
]);

const AI_BLOCKED_STATUSES = [
  "pending",
  "determination_needed",
  "sent",
  "expired",
  "declined",
  "advisory_acknowledgment_needed",
];

// ─── Tests ──────────────────────────────────────────────────────────────────

describe("fmtDate", () => {
  it("returns em dash for null", () => {
    expect(fmtDate(null)).toBe("\u2014");
  });

  it("returns em dash for undefined", () => {
    expect(fmtDate(undefined)).toBe("\u2014");
  });

  it("formats a valid ISO date", () => {
    // Use a full ISO timestamp to avoid timezone offset issues
    const result = fmtDate("2025-06-15T12:00:00Z");
    expect(result).toContain("Jun");
    expect(result).toContain("15");
    expect(result).toContain("2025");
  });
});

describe("todayISO", () => {
  it("returns today in YYYY-MM-DD format", () => {
    const result = todayISO();
    expect(result).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    // Should be today
    const today = new Date().toISOString().slice(0, 10);
    expect(result).toBe(today);
  });
});

describe("oneYearFromISO", () => {
  it("adds exactly one year", () => {
    expect(oneYearFromISO("2025-03-15")).toBe("2026-03-15");
  });

  it("handles leap year edge case", () => {
    // Feb 29 in a leap year → Mar 1 next year (no Feb 29)
    const result = oneYearFromISO("2024-02-29");
    expect(result).toBe("2025-03-01");
  });

  it("handles year boundary", () => {
    expect(oneYearFromISO("2025-12-31")).toBe("2026-12-31");
  });
});

describe("daysSince", () => {
  it("returns null for null input", () => {
    expect(daysSince(null)).toBeNull();
  });

  it("returns null for undefined input", () => {
    expect(daysSince(undefined)).toBeNull();
  });

  it("returns 0 for today", () => {
    const today = new Date().toISOString();
    expect(daysSince(today)).toBe(0);
  });

  it("returns positive for past dates", () => {
    const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString();
    const result = daysSince(weekAgo);
    expect(result).toBeGreaterThanOrEqual(6);
    expect(result).toBeLessThanOrEqual(7);
  });
});

describe("isValidEmail", () => {
  it("accepts valid emails", () => {
    expect(isValidEmail("test@example.com")).toBe(true);
    expect(isValidEmail("user.name@domain.co")).toBe(true);
    expect(isValidEmail("a@b.c")).toBe(true);
  });

  it("rejects invalid emails", () => {
    expect(isValidEmail("")).toBe(false);
    expect(isValidEmail("not-an-email")).toBe(false);
    expect(isValidEmail("@domain.com")).toBe(false);
    expect(isValidEmail("user@")).toBe(false);
    expect(isValidEmail("user @domain.com")).toBe(false);
  });
});

describe("consent status classification", () => {
  it("AI-allowed statuses are correct", () => {
    expect(AI_ALLOWED_STATUSES.has("obtained")).toBe(true);
    expect(AI_ALLOWED_STATUSES.has("acknowledged")).toBe(true);
    expect(AI_ALLOWED_STATUSES.has("not_required")).toBe(true);
    expect(AI_ALLOWED_STATUSES.size).toBe(3);
  });

  it("AI-blocked statuses don't overlap with allowed", () => {
    for (const status of AI_BLOCKED_STATUSES) {
      expect(AI_ALLOWED_STATUSES.has(status)).toBe(false);
    }
  });

  it("all known statuses are classified", () => {
    const allStatuses = [
      "obtained",
      "acknowledged",
      "not_required",
      "pending",
      "determination_needed",
      "sent",
      "expired",
      "declined",
      "advisory_acknowledgment_needed",
    ];
    for (const status of allStatuses) {
      const classified =
        AI_ALLOWED_STATUSES.has(status) ||
        AI_BLOCKED_STATUSES.includes(status);
      expect(classified).toBe(true);
    }
  });
});
