import { test, expect } from "@playwright/test";

// Full user-facing auth flow against the stack booted by docker-compose.
// The backend is real but LLM calls are short-circuited by a test API key,
// so we stay within the auth + navigation surface.

const password = "correct-horse-battery-staple";

// timeout: the first request into a cold worker can pay for the embedding model
// load (rag/retrieve.py builds SentenceTransformer at import, gunicorn runs
// several workers with no preload, and this job caches no HuggingFace data),
// which can outrun the 30s default. Only the patience changes here — every
// assertion below is unchanged.
test.describe.configure({ mode: "serial", timeout: 90_000 });

// A fresh email per attempt keeps the test hermetic against a persistent Mongo.
// This must be regenerated in beforeAll rather than at module scope: on a retry
// the module-level value would already be registered by the failed attempt, so
// sign-up would fail with "email already exists" and the retry could never pass.
// In serial mode beforeAll re-runs with the group, so tests 2 and 3 still share
// the address that test 1 registered.
let email;
test.beforeAll(() => {
  email = `e2e+${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
});

test("registers a new account from the sign-up form", async ({ page }) => {
  await page.goto("/login");

  // Flip the form into sign-up mode via the mode-switch button.
  await page.getByRole("button", { name: /^sign up$/i }).click();

  await page.getByPlaceholder("Full Name").fill("E2E User");
  await page.getByPlaceholder("Email id").fill(email);
  // getByPlaceholder matches by substring, so "Password" also matches the
  // "Confirm Password" field — exact is required to disambiguate them.
  await page.getByPlaceholder("Password", { exact: true }).fill(password);
  await page.getByPlaceholder("Confirm Password").fill(password);

  await page.getByRole("button", { name: /^sign up$/i }).click();

  // Landing on "/" means AppContext successfully set the token and navigated.
  // Poll for navigation *or* the inline error, so a rejected sign-up reports the
  // backend's message instead of an unexplained 30s waitForURL timeout.
  await expect
    .poll(
      async () => {
        if (new URL(page.url()).pathname === "/") return "navigated";
        const err = page.locator("p.text-red-500");
        if (await err.isVisible()) return `sign-up rejected: ${await err.innerText()}`;
        return "pending";
      },
      { timeout: 60_000, message: "sign-up did not navigate to /" }
    )
    .toBe("navigated");
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
  await page.getByPlaceholder("Password", { exact: true }).fill(password);
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
  await page.getByPlaceholder("Password", { exact: true }).fill("definitely-wrong");
  await page.getByRole("button", { name: /^login$/i }).click();

  // We should stay on /login and surface an error. The exact copy comes from
  // the backend; assert the URL and that *some* red-text error is visible.
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.locator("p.text-red-500")).toBeVisible();
});
