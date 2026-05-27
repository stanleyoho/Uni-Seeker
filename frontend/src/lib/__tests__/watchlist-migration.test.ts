import { beforeEach, describe, expect, it, vi } from "vitest";

// Hoisted mock state so vi.mock() factory captures it without ReferenceError.
const { addToWatchlistMock, listWatchlistMock } = vi.hoisted(() => ({
  addToWatchlistMock: vi.fn(),
  listWatchlistMock: vi.fn(),
}));

vi.mock("@/lib/api-client", async () => {
  // Re-export the real ApiError class so `err instanceof ApiError` works
  // inside the SUT's classifyError, but stub the network functions.
  const actual = await vi.importActual<typeof import("@/lib/api-client")>(
    "@/lib/api-client",
  );
  return {
    ...actual,
    addToWatchlist: addToWatchlistMock,
    listWatchlist: listWatchlistMock,
  };
});

import { ApiError } from "@/lib/api-client";
import {
  hasLegacyWatchlist,
  migrateLocalWatchlistToApi,
} from "@/lib/watchlist-migration";

const KEY = "uni-seeker-watchlist";

describe("hasLegacyWatchlist", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns false when the legacy key is absent", () => {
    expect(hasLegacyWatchlist()).toBe(false);
  });

  it("returns true even for an empty array — it only checks presence", () => {
    localStorage.setItem(KEY, "[]");
    expect(hasLegacyWatchlist()).toBe(true);
  });
});

describe("migrateLocalWatchlistToApi", () => {
  beforeEach(() => {
    localStorage.clear();
    addToWatchlistMock.mockReset();
    listWatchlistMock.mockReset();
  });

  it("returns zeros and clears the key when localStorage is empty", async () => {
    const result = await migrateLocalWatchlistToApi();
    expect(result).toEqual({ migrated: 0, skipped: 0, failed: [] });
    expect(listWatchlistMock).not.toHaveBeenCalled();
    expect(addToWatchlistMock).not.toHaveBeenCalled();
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("filters out malformed legacy rows before migrating", async () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([
        { symbol: "2330" },
        { symbol: "" }, // empty string — skipped
        { notSymbol: "garbage" }, // wrong shape — skipped
        null, // null entry — skipped
        { symbol: "2317" },
      ]),
    );
    listWatchlistMock.mockResolvedValue([]);
    addToWatchlistMock.mockResolvedValue({ symbol: "ok", added_at: "" });

    const result = await migrateLocalWatchlistToApi();

    expect(addToWatchlistMock).toHaveBeenCalledTimes(2);
    expect(addToWatchlistMock).toHaveBeenNthCalledWith(1, "2330");
    expect(addToWatchlistMock).toHaveBeenNthCalledWith(2, "2317");
    expect(result.migrated).toBe(2);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("pre-skips symbols already present on the server", async () => {
    localStorage.setItem(KEY, JSON.stringify([{ symbol: "2330" }, { symbol: "2317" }]));
    listWatchlistMock.mockResolvedValue([{ symbol: "2330", added_at: "" }]);
    addToWatchlistMock.mockResolvedValue({ symbol: "2317", added_at: "" });

    const result = await migrateLocalWatchlistToApi();

    expect(addToWatchlistMock).toHaveBeenCalledTimes(1);
    expect(addToWatchlistMock).toHaveBeenCalledWith("2317");
    expect(result).toMatchObject({ migrated: 1, skipped: 1, failed: [] });
  });

  it("treats 409 conflict from addToWatchlist as `skipped`, not failed", async () => {
    localStorage.setItem(KEY, JSON.stringify([{ symbol: "2330" }]));
    listWatchlistMock.mockResolvedValue([]);
    addToWatchlistMock.mockRejectedValue(new ApiError("dupe", 409));

    const result = await migrateLocalWatchlistToApi();
    expect(result).toEqual({ migrated: 0, skipped: 1, failed: [] });
  });

  it("stops on 403 watchlist_limit_exceeded and marks the rest as tier_cap", async () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([{ symbol: "A" }, { symbol: "B" }, { symbol: "C" }]),
    );
    listWatchlistMock.mockResolvedValue([]);
    addToWatchlistMock
      .mockResolvedValueOnce({ symbol: "A", added_at: "" })
      .mockRejectedValueOnce(new ApiError("watchlist_limit_exceeded", 403))
      .mockResolvedValueOnce({ symbol: "C", added_at: "" }); // never called

    const result = await migrateLocalWatchlistToApi();

    expect(addToWatchlistMock).toHaveBeenCalledTimes(2);
    expect(result.migrated).toBe(1);
    expect(result.skipped).toBe(0);
    expect(result.failed).toEqual([
      { symbol: "B", reason: "tier_cap" },
      { symbol: "C", reason: "tier_cap" },
    ]);
  });

  it("maps 404 → unknown_symbol, 422 → invalid_symbol, 401 → unauthenticated", async () => {
    localStorage.setItem(
      KEY,
      JSON.stringify([{ symbol: "X" }, { symbol: "Y" }, { symbol: "Z" }]),
    );
    listWatchlistMock.mockResolvedValue([]);
    addToWatchlistMock
      .mockRejectedValueOnce(new ApiError("nope", 404))
      .mockRejectedValueOnce(new ApiError("bad", 422))
      .mockRejectedValueOnce(new ApiError("auth", 401));

    const result = await migrateLocalWatchlistToApi();
    expect(result.failed).toEqual([
      { symbol: "X", reason: "unknown_symbol" },
      { symbol: "Y", reason: "invalid_symbol" },
      { symbol: "Z", reason: "unauthenticated" },
    ]);
    expect(result.migrated).toBe(0);
  });

  it("classifies a non-ApiError throw as `network`", async () => {
    localStorage.setItem(KEY, JSON.stringify([{ symbol: "2330" }]));
    listWatchlistMock.mockResolvedValue([]);
    addToWatchlistMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const result = await migrateLocalWatchlistToApi();
    expect(result.failed).toEqual([{ symbol: "2330", reason: "network" }]);
  });

  it("aborts before mutating if listWatchlist() fails, and does NOT clear the key", async () => {
    localStorage.setItem(KEY, JSON.stringify([{ symbol: "2330" }]));
    listWatchlistMock.mockRejectedValue(new ApiError("server down", 500));

    const result = await migrateLocalWatchlistToApi();

    expect(addToWatchlistMock).not.toHaveBeenCalled();
    expect(result).toEqual({
      migrated: 0,
      skipped: 0,
      failed: [{ symbol: "2330", reason: "api_500" }],
    });
    // Legacy key MUST survive so the user can retry — the SUT bails before
    // the clearLegacy() call when the remote view is unavailable.
    expect(localStorage.getItem(KEY)).not.toBeNull();
  });

  it("swallows corrupt JSON in the legacy key and treats it as empty", async () => {
    localStorage.setItem(KEY, "{not json");
    const result = await migrateLocalWatchlistToApi();
    expect(result).toEqual({ migrated: 0, skipped: 0, failed: [] });
    expect(listWatchlistMock).not.toHaveBeenCalled();
    // Empty-migration path clears the key.
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});
