import { test, expect } from "@playwright/test";

// Smoke test: the app loads and we can reach a visible landmark.
// Intentionally minimal — broader E2E comes later.
test("app loads the landing/login page", async ({ page }) => {
  const response = await page.goto("/", { waitUntil: "domcontentloaded" });
  expect(response?.ok()).toBeTruthy();

  // The app is a React SPA; we just assert the root node rendered anything.
  await expect(page.locator("#root")).not.toBeEmpty({ timeout: 10_000 });
});

test("health endpoint is reachable via proxy", async ({ request }) => {
  const r = await request.get("/api/v1/health");
  expect(r.ok()).toBeTruthy();
  const body = await r.json();
  expect(body.status).toBe("healthy");
});
