import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Vitest config for the frontend unit suite. Playwright E2E specs live under
// ./tests/e2e and are excluded here so `npm test` only runs jsdom unit tests.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
    css: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/assets/**",
        "src/**/*.test.{ts,tsx}",
        "src/test/**",
        "src/types/**",
      ],
    },
  },
});
