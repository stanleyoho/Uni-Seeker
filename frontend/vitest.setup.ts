// Global test setup. Adds jest-dom matchers (toBeInTheDocument, etc.) onto
// Vitest's `expect`, and installs a global `fetch` mock so api-client tests
// never make a real network call. Individual tests reset / re-stub `fetch`
// in their own `beforeEach`.
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Node 25 ships a stub `localStorage` (object with no methods) behind the
// `--localstorage-file` flag — and that stub shadows BOTH globalThis AND
// jsdom's window.localStorage after vitest's populateGlobal runs. So we
// install a minimal, in-memory, fully-functional polyfill that production
// code can call into. api-client and watchlist-migration both assume the
// Web Storage API contract (setItem / getItem / removeItem / clear).
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length(): number {
    return this.store.size;
  }
  clear(): void {
    this.store.clear();
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

const memoryLocalStorage = new MemoryStorage();
Object.defineProperty(globalThis, "localStorage", {
  value: memoryLocalStorage,
  configurable: true,
  writable: true,
});
if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", {
    value: memoryLocalStorage,
    configurable: true,
    writable: true,
  });
}

// Default `fetch` to a vi.fn so any accidental un-stubbed call throws with
// a useful error instead of attempting real network IO.
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => {
      throw new Error(
        "fetch was called without a per-test stub. Set globalThis.fetch in your test.",
      );
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
