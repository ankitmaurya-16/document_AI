import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Node 25 ships experimental webstorage which, when enabled by the host,
// can shadow jsdom's localStorage with a broken implementation. Install a
// plain in-memory shim so tests don't depend on the host's storage state.
function installStorageShim() {
  const make = () => {
    let store: Record<string, string> = {};
    return {
      getItem: (k: string) => (k in store ? store[k] : null),
      setItem: (k: string, v: string) => {
        store[k] = String(v);
      },
      removeItem: (k: string) => {
        delete store[k];
      },
      clear: () => {
        store = {};
      },
      key: (i: number) => Object.keys(store)[i] ?? null,
      get length() {
        return Object.keys(store).length;
      },
    } as Storage;
  };
  Object.defineProperty(window, "localStorage", { value: make(), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: make(), writable: true });
}

installStorageShim();

// jsdom doesn't implement Element.scrollTo; components that auto-scroll on
// mount would otherwise crash with "scrollTo is not a function".
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = (() => {}) as typeof Element.prototype.scrollTo;
}

// Isolate each test: clear jsdom, timers, mocks, and storage.
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  try {
    window.localStorage?.clear?.();
    window.sessionStorage?.clear?.();
  } catch {
    // Defensive: storage is shimmed above, but a test may have replaced it.
  }
});

// matchMedia is referenced by tailwind's dark-mode toggles; jsdom doesn't ship
// it. Stub out just enough for code under test to read `.matches`.
beforeEach(() => {
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  }
});
