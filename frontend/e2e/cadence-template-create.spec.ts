/**
 * E2E happy-path: admin creates a custom cadence template via Settings UI.
 *
 * Covers G4-P4d Surface B — org-level template management.
 *
 * Run: PLAYWRIGHT_BASE_URL=https://callwen.com npx playwright test cadence-template-create
 */
import { test, expect } from "@playwright/test";
import { signIn } from "./helpers/auth";

test.describe("Cadence template creation (G4-P4d)", () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page);
  });

  let createdTemplateName = "";

  test("admin creates a custom template, sees it in the list, can navigate into it", async ({
    page,
  }) => {
    // (a) Navigate to cadence templates settings
    await page.goto("/dashboard/settings/cadence-templates");
    await expect(
      page.getByRole("heading", { name: "Cadence Templates" }),
    ).toBeVisible();

    // (b) System templates section is visible
    await expect(
      page.getByRole("heading", { name: "System templates" }),
    ).toBeVisible();

    // (c) Generate unique template name
    const templateName = `E2E test template ${Date.now()}`;
    createdTemplateName = templateName;

    // (d) Open create dialog
    await page.getByRole("button", { name: "+ New custom template" }).click();

    // (e) Fill name and description
    await expect(
      page.getByRole("heading", { name: "Create Custom Template" }),
    ).toBeVisible();
    await page
      .getByPlaceholder("e.g. Quarterly Focus")
      .fill(templateName);
    await page
      .getByPlaceholder("Optional description")
      .fill("created by playwright");

    // (f) Toggle first 3 deliverable flags
    await page.getByLabel("Kickoff memo").check();
    await page.getByLabel("Progress note").check();
    await page.getByLabel("Quarterly memo").check();

    // (g) Submit
    await page.getByRole("button", { name: "Create" }).click();

    // (h) Dialog closes — heading disappears
    await expect(
      page.getByRole("heading", { name: "Create Custom Template" }),
    ).not.toBeVisible({ timeout: 10_000 });

    // (i) New template appears in custom section
    await expect(page.getByText(templateName)).toBeVisible({
      timeout: 10_000,
    });

    // (j) Click into the template detail
    await page.getByText(templateName).click();
    await page.waitForURL(/\/dashboard\/settings\/cadence-templates\/.+/);

    // (k) Detail page renders with template name + editable fields + deactivate
    await expect(
      page.getByRole("heading", { name: templateName }),
    ).toBeVisible();
    await expect(page.getByText("Danger zone")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Deactivate template" }),
    ).toBeVisible();
  });

  test.afterEach(async ({ page }) => {
    // Best-effort cleanup: deactivate the template we created
    if (!createdTemplateName) return;
    try {
      // Navigate to cadence templates list
      await page.goto("/dashboard/settings/cadence-templates");
      await expect(
        page.getByRole("heading", { name: "Cadence Templates" }),
      ).toBeVisible({ timeout: 10_000 });

      // Find and click the created template
      const templateLink = page.getByText(createdTemplateName);
      if ((await templateLink.count()) === 0) return;
      await templateLink.click();
      await page.waitForURL(/\/dashboard\/settings\/cadence-templates\/.+/);

      // Click deactivate
      const deactivateBtn = page.getByRole("button", {
        name: "Deactivate template",
      });
      if ((await deactivateBtn.count()) > 0) {
        await deactivateBtn.click();
        // Wait for redirect back to list
        await page.waitForURL("**/dashboard/settings/cadence-templates", {
          timeout: 10_000,
        });
      }
    } catch {
      // Cleanup is best-effort — log and move on
      console.warn(
        `[cleanup] Could not deactivate template "${createdTemplateName}"`,
      );
    }
  });
});
