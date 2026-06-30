import { test, expect } from "@playwright/test";

// Full user-facing auth flow against the stack booted by docker-compose.
// The backend is real but LLM calls are short-circuited by a test API key,
// so we stay within the auth + navigation surface.

// A fresh email per run keeps the test hermetic even against a persistent Mongo.
const email = `e2e+${Date.now()}@example.com`;
const password = "correct-horse-battery-staple";

test.describe.configure({ mode: "serial" });

test("registers a new account from the sign-up form", async ({ page }) => {
  await page.goto("/login");

  // Flip the form into sign-up mode via the mode-switch button.
  await page.getByRole("button", { name: /^sign up$/i }).click();

  await page.getByPlaceholder("Full Name").fill("E2E User");
  await page.getByPlaceholder("Email id").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByPlaceholder("Confirm Password").fill(password);

  await page.getByRole("button", { name: /^sign up$/i }).click();

  // Landing on "/" means AppContext successfully set the token and navigated.
  await page.waitForURL("/");
  // Token should be persisted for the next test in the serial group.
  const token = await page.evaluate(() => localStorage.getItem("token"));
  expect(token).toBeTruthy();
});

test("logs out and signs back in with the same credentials", async ({ page, context }) => {
  // Clear storage to simulate a fresh visitor with known credentials.
  await context.clearCookies();
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.reload();

  await page.getByPlaceholder("Email id").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.getByRole("button", { name: /^login$/i }).click();

  await page.waitForURL("/");
  const token = await page.evaluate(() => localStorage.getItem("token"));
  expect(token).toBeTruthy();
});

test("rejects a bad password with an inline error", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/login");
  await page.evaluate(() => localStorage.clear());
  await page.reload();

  await page.getByPlaceholder("Email id").fill(email);
  await page.getByPlaceholder("Password").fill("definitely-wrong");
  await page.getByRole("button", { name: /^login$/i }).click();

  // We should stay on /login and surface an error. The exact copy comes from
  // the backend; assert the URL and that *some* red-text error is visible.
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator("p.text-red-500")).toBeVisible();
});
