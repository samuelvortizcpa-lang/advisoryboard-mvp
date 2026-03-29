/**
 * E2E auth helper — signs in via Clerk's development UI.
 *
 * Requires TEST_USER_EMAIL and TEST_USER_PASSWORD in .env.test (gitignored).
 * Uses a real test account on Clerk's development instance.
 */
import { Page } from "@playwright/test";

export async function signIn(page: Page) {
  await page.goto("/sign-in");

  // Wait for Clerk to render its sign-in component
  await page.waitForSelector(".cl-signIn-root, .cl-rootBox", {
    timeout: 10_000,
  });

  const email = process.env.TEST_USER_EMAIL;
  const password = process.env.TEST_USER_PASSWORD;

  if (!email || !password) {
    throw new Error(
      "TEST_USER_EMAIL and TEST_USER_PASSWORD must be set in .env.test"
    );
  }

  // Clerk sign-in: enter email
  await page.fill('input[name="identifier"]', email);
  await page.click(".cl-formButtonPrimary");

  // Clerk sign-in: enter password
  await page.waitForSelector('input[type="password"]', { timeout: 5_000 });
  await page.fill('input[type="password"]', password);
  await page.click(".cl-formButtonPrimary");

  // Wait for redirect to dashboard
  await page.waitForURL("**/dashboard**", { timeout: 15_000 });
}
