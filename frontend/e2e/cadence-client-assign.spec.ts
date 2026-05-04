/**
 * E2E happy-path: admin assigns a cadence template to a client and toggles
 * a deliverable override.
 *
 * Covers G4-P4d Surface A — client-level cadence assignment.
 *
 * Requires TEST_CLIENT_ID in .env.test (UUID of the E2E Test Client).
 *
 * Run: PLAYWRIGHT_BASE_URL=https://callwen.com npx playwright test cadence-client-assign
 */
import { test, expect } from "@playwright/test";
import { signIn } from "./helpers/auth";

const clientId = process.env.TEST_CLIENT_ID;

test.describe("Cadence client assignment (G4-P4d)", () => {
  test.beforeEach(async ({ page }) => {
    if (!clientId) throw new Error("TEST_CLIENT_ID required in .env.test");
    await signIn(page);
  });

  test("admin assigns a template to a client, toggles an override, override persists across reload", async ({
    page,
  }) => {
    // (a) Navigate to client detail
    await page.goto(`/dashboard/clients/${clientId}`);
    await page.waitForLoadState("networkidle");

    // (b) Click the Cadence tab
    await page.getByRole("tab", { name: "Cadence" }).or(
      page.locator('[role="tab"]').filter({ hasText: "Cadence" }),
    ).or(
      page.getByText("Cadence", { exact: true }),
    ).first().click();

    // Wait for cadence content to load (either empty state or active card)
    await expect(
      page.getByText("No cadence assigned").or(
        page.getByText("of 7 deliverables enabled"),
      ),
    ).toBeVisible({ timeout: 10_000 });

    // (c-d) Idempotent assign: only run the assign flow if not already on Quarterly Only
    const alreadyOnQuarterlyOnly = await page
      .getByRole("heading", { name: "Quarterly Only" })
      .isVisible({ timeout: 2_000 })
      .catch(() => false);

    if (!alreadyOnQuarterlyOnly) {
      const pickBtn = page.getByRole("button", { name: "Pick template" });
      const changeBtn = page.getByRole("button", { name: "Change" });

      if (await pickBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await pickBtn.click();
      } else {
        await changeBtn.click();
      }

      // (e) Drawer opens — select "Quarterly Only"
      await expect(
        page.getByRole("heading", { name: "Assign cadence template" }),
      ).toBeVisible({ timeout: 10_000 });

      await page
        .locator("button")
        .filter({ hasText: "Quarterly Only" })
        .click();

      // Click Confirm
      await page.getByRole("button", { name: "Confirm" }).click();

      // Drawer closes
      await expect(
        page.getByRole("heading", { name: "Assign cadence template" }),
      ).not.toBeVisible({ timeout: 10_000 });
    }

    // (f) Verify ActiveCadenceCard shows "Quarterly Only" (regardless of path above)
    await expect(
      page.getByRole("heading", { name: "Quarterly Only" }),
    ).toBeVisible();
    await expect(page.getByText(/\d+ of 7 deliverables enabled/)).toBeVisible();

    // (g) Verify deliverables grid renders
    await expect(page.getByText("Deliverables", { exact: true })).toBeVisible();

    // (h) Reset to clean state, then toggle Kickoff memo on
    // Idempotence: if overrides exist from a stale state, reset them first
    const resetBtn = page.getByRole("button", { name: "Reset all" });
    if (await resetBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await resetBtn.click();
      await expect(
        page.getByText("All deliverables follow template defaults"),
      ).toBeVisible({ timeout: 5_000 });
    }

    const kickoffCheckbox = page.getByLabel("Kickoff memo");
    await expect(kickoffCheckbox).not.toBeChecked();
    await kickoffCheckbox.check();

    // Override count should update
    await expect(
      page.getByText("1 of 7 currently overridden"),
    ).toBeVisible({ timeout: 5_000 });

    // "override" badge should appear next to Kickoff memo
    await expect(page.getByText("override").first()).toBeVisible();

    // (i) Reload the page
    await page.reload();
    await page.waitForLoadState("networkidle");

    // Re-click Cadence tab after reload
    await page.getByRole("tab", { name: "Cadence" }).or(
      page.locator('[role="tab"]').filter({ hasText: "Cadence" }),
    ).or(
      page.getByText("Cadence", { exact: true }),
    ).first().click();

    // (j) Re-verify: same template, override persists
    await expect(
      page.getByRole("heading", { name: "Quarterly Only" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByLabel("Kickoff memo")).toBeChecked();
    await expect(
      page.getByText("1 of 7 currently overridden"),
    ).toBeVisible();
  });

  test.afterEach(async ({ page }) => {
    // Best-effort cleanup: reset overrides by re-assigning the same template
    if (!clientId) return;
    try {
      await page.goto(`/dashboard/clients/${clientId}`);
      await page.waitForLoadState("networkidle");

      // Click Cadence tab
      await page.getByRole("tab", { name: "Cadence" }).or(
        page.locator('[role="tab"]').filter({ hasText: "Cadence" }),
      ).or(
        page.getByText("Cadence", { exact: true }),
      ).first().click();

      // Wait for content
      await expect(
        page.getByText("of 7 deliverables enabled").or(
          page.getByText("No cadence assigned"),
        ),
      ).toBeVisible({ timeout: 10_000 });

      // Click "Reset all" if visible (clears overrides)
      const resetBtn = page.getByRole("button", { name: "Reset all" });
      if (await resetBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
        await resetBtn.click();
        // Wait for override count to disappear
        await expect(
          page.getByText("All deliverables follow template defaults"),
        ).toBeVisible({ timeout: 5_000 });
      }
    } catch {
      console.warn("[cleanup] Could not reset cadence overrides");
    }
  });
});
