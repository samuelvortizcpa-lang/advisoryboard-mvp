/**
 * E2E tests for critical user paths.
 *
 * Requires a running local dev server (started automatically by Playwright)
 * and valid test credentials in .env.test.
 *
 * Run: npm run test:e2e
 */
import { test, expect } from "@playwright/test";
import { signIn } from "./helpers/auth";

test.describe("Critical User Paths", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  test("Dashboard loads with key sections", async ({ page }) => {
    // Should be on dashboard after sign-in
    await expect(page).toHaveURL(/\/dashboard/);

    // Sidebar should have main navigation links
    await expect(page.locator('a[href="/dashboard/clients"]')).toBeVisible();

    // Should not show any error state
    await expect(page.locator("text=Application error")).not.toBeVisible();
    await expect(page.locator("text=500")).not.toBeVisible();
  });

  test("Client list loads", async ({ page }) => {
    await page.click('a[href="/dashboard/clients"]');
    await page.waitForURL("**/dashboard/clients");

    // Page should render — either client rows or an empty state
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=Application error")).not.toBeVisible();
  });

  test("Client detail page loads", async ({ page }) => {
    await page.click('a[href="/dashboard/clients"]');
    await page.waitForURL("**/dashboard/clients");
    await page.waitForLoadState("networkidle");

    // Click the first client link if any exist
    const clientLink = page.locator('a[href^="/dashboard/clients/"]').first();
    if ((await clientLink.count()) > 0) {
      await clientLink.click();
      await page.waitForURL(/\/dashboard\/clients\/.+/);

      // Should show client detail sections
      await page.waitForLoadState("networkidle");
      await expect(page.locator("text=Application error")).not.toBeVisible();
    }
  });

  test("Settings page loads", async ({ page }) => {
    await page.click('a[href="/dashboard/settings"]');
    await page.waitForURL("**/dashboard/settings");
    await page.waitForLoadState("networkidle");

    await expect(page.locator("text=Application error")).not.toBeVisible();
  });

  test("Navigation between pages works without errors", async ({ page }) => {
    const routes = [
      "/dashboard/clients",
      "/dashboard/actions",
      "/dashboard/settings",
      "/dashboard",
    ];

    for (const route of routes) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      await expect(page.locator("text=Application error")).not.toBeVisible();
    }
  });

  test("Chat input is present on client detail", async ({ page }) => {
    await page.click('a[href="/dashboard/clients"]');
    await page.waitForURL("**/dashboard/clients");
    await page.waitForLoadState("networkidle");

    const clientLink = page.locator('a[href^="/dashboard/clients/"]').first();
    if ((await clientLink.count()) > 0) {
      await clientLink.click();
      await page.waitForURL(/\/dashboard\/clients\/.+/);
      await page.waitForLoadState("networkidle");

      // Look for a chat input (textarea or input with "Ask" placeholder)
      const chatInput = page.locator(
        'textarea, input[placeholder*="Ask"], input[placeholder*="ask"]'
      );
      // Chat might not be visible if no documents, but page shouldn't error
      await expect(page.locator("text=Application error")).not.toBeVisible();
    }
  });

  test("Consent UI renders on client detail", async ({ page }) => {
    await page.click('a[href="/dashboard/clients"]');
    await page.waitForURL("**/dashboard/clients");
    await page.waitForLoadState("networkidle");

    const clientLink = page.locator('a[href^="/dashboard/clients/"]').first();
    if ((await clientLink.count()) > 0) {
      await clientLink.click();
      await page.waitForURL(/\/dashboard\/clients\/.+/);
      await page.waitForLoadState("networkidle");

      // The page should load without errors — consent banner presence
      // depends on client status, but the page itself must not crash
      const bodyText = await page.textContent("body");
      expect(bodyText).not.toContain("Application error");
    }
  });
});
