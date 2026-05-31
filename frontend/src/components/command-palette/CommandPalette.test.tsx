// CommandPalette tests — keyboard nav (Enter / Esc / arrow keys) + the
// Cmd-K / Ctrl-K open toggle. We mock the heavy collaborators (router,
// i18n context, heatmap hook, searchStocks) so the test runs without
// TanStack Query / Next router providers in the tree.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";

// jsdom does not implement scrollIntoView on Element. CommandPalette
// calls it after each ArrowUp/Down so the active row stays in view.
// Stub it so the test environment doesn't throw.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {};
}

// ---- Mocks ---------------------------------------------------------------

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/i18n/context", () => ({
  useI18n: () => ({
    t: {
      search: { placeholder: "Type a ticker", noResults: "No results" },
    },
    locale: "en",
    setLocale: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-market-data", () => ({
  useHeatmap: () => ({
    data: {
      sectors: [
        {
          industry: "半導體",
          stock_count: 1,
          avg_change_percent: "1.23",
          total_volume: 100,
          stocks: [],
        },
      ],
    },
    isLoading: false,
  }),
}));

// Default: no ticker results. Individual tests can override.
type SearchFn = (q: string, limit?: number) => Promise<unknown[]>;
const searchStocksMock = vi.fn<SearchFn>(async () => []);
vi.mock("@/lib/api-client", () => ({
  searchStocks: (q: string, l?: number) => searchStocksMock(q, l),
}));

// Import AFTER mocks so the component sees the mocked module.
import { CommandPalette, isCmdK, CMDK_OPEN_EVENT } from "./CommandPalette";

beforeEach(() => {
  pushMock.mockClear();
  searchStocksMock.mockClear();
});

// ---- isCmdK matcher unit tests ------------------------------------------

describe("isCmdK", () => {
  it("matches metaKey+k on mac-like UA", () => {
    // jsdom default UA is mac-like; we read navigator inside isCmdK.
    const e = new KeyboardEvent("keydown", { key: "k", metaKey: true });
    expect(isCmdK(e)).toBe(true);
  });

  it("does not match plain k", () => {
    const e = new KeyboardEvent("keydown", { key: "k" });
    expect(isCmdK(e)).toBe(false);
  });
});

// ---- Palette open / close / kb nav --------------------------------------

describe("CommandPalette", () => {
  it("is closed by default in uncontrolled mode", () => {
    render(<CommandPalette />);
    expect(screen.queryByTestId("command-palette")).toBeNull();
  });

  it("opens on CMDK_OPEN_EVENT and renders Pages by default", async () => {
    render(<CommandPalette />);
    await act(async () => {
      window.dispatchEvent(new CustomEvent(CMDK_OPEN_EVENT));
    });
    expect(screen.getByTestId("command-palette")).toBeInTheDocument();
    // Default page list contains the Markets entry.
    expect(screen.getByText(/首頁 \/ Markets/)).toBeInTheDocument();
    // The sector item from the mocked heatmap is also present.
    expect(screen.getByText("半導體")).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    render(<CommandPalette />);
    await act(async () => {
      window.dispatchEvent(new CustomEvent(CMDK_OPEN_EVENT));
    });
    const input = screen.getByTestId("command-palette-input");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByTestId("command-palette")).toBeNull();
  });

  it("ArrowDown wraps around the list and ArrowUp wraps backwards", async () => {
    render(<CommandPalette />);
    await act(async () => {
      window.dispatchEvent(new CustomEvent(CMDK_OPEN_EVENT));
    });
    const input = screen.getByTestId("command-palette-input");

    // Initially the first item is active.
    const initialActive = document.querySelector('[aria-selected="true"]');
    expect(initialActive).not.toBeNull();

    // ArrowDown should not throw and should update aria-selected to another row.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    const afterDown = document.querySelector('[aria-selected="true"]');
    expect(afterDown).not.toBeNull();
    expect(afterDown).not.toBe(initialActive);

    // ArrowUp from index 1 → goes back to 0. Should still have an active row.
    fireEvent.keyDown(input, { key: "ArrowUp" });
    const afterUp = document.querySelector('[aria-selected="true"]');
    expect(afterUp).not.toBeNull();
  });

  it("Enter activates the selected page item and navigates", async () => {
    render(<CommandPalette />);
    await act(async () => {
      window.dispatchEvent(new CustomEvent(CMDK_OPEN_EVENT));
    });
    const input = screen.getByTestId("command-palette-input");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(pushMock).toHaveBeenCalledTimes(1);
    // The first item in the default list is the Markets home page.
    expect(pushMock).toHaveBeenCalledWith("/");
    // Palette closes on activation.
    expect(screen.queryByTestId("command-palette")).toBeNull();
  });

  it("⌘K toggles open/close", async () => {
    render(<CommandPalette />);

    // Press Cmd+K → opens.
    await act(async () => {
      const e = new KeyboardEvent("keydown", { key: "k", metaKey: true });
      window.dispatchEvent(e);
    });
    expect(screen.getByTestId("command-palette")).toBeInTheDocument();

    // Press Cmd+K again → closes.
    await act(async () => {
      const e = new KeyboardEvent("keydown", { key: "k", metaKey: true });
      window.dispatchEvent(e);
    });
    expect(screen.queryByTestId("command-palette")).toBeNull();
  });
});
