import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  addToWatchlist,
  fetchWatchlistIndicators,
  listWatchlist,
  removeFromWatchlist,
} from "@/lib/api-client";

// ---------------------------------------------------------------------------
// Test scope
//
// `apiFetch` and `getAuthHeaders` are not exported, so we exercise them
// indirectly through `listWatchlist` (GET), `addToWatchlist` (POST + body),
// and `removeFromWatchlist` (DELETE + non-JSON-shaped 200 body). This covers:
//   - 200 happy path
//   - 401 / 404 / 5xx error mapping → ApiError with .status, .code
//   - timeout (AbortError → ApiError 408 "TIMEOUT")
//   - network failure (TypeError → ApiError 0 "NETWORK_ERROR")
//   - Authorization header injection from localStorage["auth_token"]
//   - empty-body responses parsed as `undefined`
// ---------------------------------------------------------------------------

// Helper: a Response-like that exposes ok/status/json/text the way apiFetch
// reads them. We avoid `new Response(...)` because some shimmed jsdom builds
// don't ship a spec-compliant Response, and apiFetch only touches these four
// properties anyway.
function jsonResponse(status: number, body: unknown): Response {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => (text ? JSON.parse(text) : {}),
    text: async () => text,
  } as unknown as Response;
}

describe("ApiError", () => {
  it("sets message, status, code, and name", () => {
    const err = new ApiError("boom", 418, "TEA");
    expect(err).toBeInstanceOf(Error);
    expect(err.message).toBe("boom");
    expect(err.status).toBe(418);
    expect(err.code).toBe("TEA");
    expect(err.name).toBe("ApiError");
  });

  it("allows code to be omitted", () => {
    const err = new ApiError("nope", 500);
    expect(err.status).toBe(500);
    expect(err.code).toBeUndefined();
  });
});

describe("apiFetch (via listWatchlist GET)", () => {
  beforeEach(() => {
    // Clean slate between tests — no leftover auth token from a previous run.
    localStorage.clear();
  });

  it("returns parsed JSON on 200 and sends Content-Type: application/json", async () => {
    const payload = [{ symbol: "2330", added_at: "2026-05-27" }];
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, payload));
    vi.stubGlobal("fetch", fetchMock);

    const result = await listWatchlist();

    expect(result).toEqual(payload);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/watchlist\/$/);
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers["Content-Type"]).toBe("application/json");
    // No token in localStorage → no Authorization header.
    expect(headers.Authorization).toBeUndefined();
  });

  it("throws ApiError(401) on 401 and preserves backend message/code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(401, { message: "Bad token", error: "AUTH_INVALID" }),
      ),
    );

    await expect(listWatchlist()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      message: "Bad token",
      code: "AUTH_INVALID",
    });
  });

  it("throws ApiError(404) and falls back to FastAPI-style `detail`", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(404, { detail: "Watchlist not found" }),
      ),
    );

    await expect(listWatchlist()).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Watchlist not found",
    });
  });

  it("throws ApiError(500) with generic fallback when body has no message/detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(500, {})),
    );

    await expect(listWatchlist()).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "Request failed: 500",
    });
  });

  it("maps AbortError (timeout) to ApiError(408, TIMEOUT)", async () => {
    // Simulate the controller aborting mid-flight by rejecting with a real
    // DOMException whose name is "AbortError" — apiFetch's catch block
    // narrows on that exact shape.
    const abortErr = new DOMException("aborted", "AbortError");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(abortErr));

    await expect(listWatchlist()).rejects.toMatchObject({
      name: "ApiError",
      status: 408,
      code: "TIMEOUT",
      message: "Request timeout",
    });
  });

  it("wraps generic network errors as ApiError(0, NETWORK_ERROR)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );

    await expect(listWatchlist()).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      code: "NETWORK_ERROR",
      message: "Failed to fetch",
    });
  });
});

describe("apiFetch auth header injection", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("includes Authorization: Bearer <token> when auth_token is present", async () => {
    localStorage.setItem("auth_token", "abc123");
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await listWatchlist();

    const [, init] = fetchMock.mock.calls[0];
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer abc123");
  });

  it("omits Authorization when no token in localStorage", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    vi.stubGlobal("fetch", fetchMock);

    await listWatchlist();

    const [, init] = fetchMock.mock.calls[0];
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });
});

describe("apiFetch POST body forwarding (via addToWatchlist)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("forwards method + body and parses 201 response", async () => {
    const created = { symbol: "2330", added_at: "2026-05-27" };
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, created));
    vi.stubGlobal("fetch", fetchMock);

    const result = await addToWatchlist("2330");

    expect(result).toEqual(created);
    const [, init] = fetchMock.mock.calls[0];
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBe(JSON.stringify({ symbol: "2330" }));
  });

  it("surfaces 409 conflict as ApiError(409) — used by watchlist-migration", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(409, { message: "already on watchlist" }),
      ),
    );

    await expect(addToWatchlist("2330")).rejects.toMatchObject({
      status: 409,
      message: "already on watchlist",
    });
  });
});

describe("fetchWatchlistIndicators (POST /watchlist/indicators)", () => {
  it("short-circuits to [] without calling fetch when symbols is empty", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchWatchlistIndicators([])).resolves.toEqual([]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("POSTs the symbols and unwraps the items array", async () => {
    const items = [
      {
        symbol: "2330.TW",
        last_price: "150.0000",
        prev_close: "140.0000",
        change: "10.0000",
        change_percent: "7.1400",
        rsi: "72.5000",
        ma_short: "148.0000",
        ma_long: "140.0000",
        ma_cross: "golden",
        pct_from_ma_long: "5.2000",
      },
    ];
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { items }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchWatchlistIndicators(["2330.TW"]);
    expect(result).toEqual(items);

    // Verify the request shape: POST with a JSON { symbols } body.
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/watchlist\/indicators$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ symbols: ["2330.TW"] });
  });

  it("propagates an ApiError on a 4xx/5xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(422, { detail: "bad" })),
    );
    await expect(
      fetchWatchlistIndicators(["2330.TW"]),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

describe("apiFetch empty body handling (via removeFromWatchlist)", () => {
  it("treats empty 200 body as undefined and does not throw", async () => {
    // Simulate a true empty response (text() returns ""). apiFetch should
    // return undefined-cast-to-T without calling JSON.parse on an empty string.
    const emptyRes = {
      ok: true,
      status: 200,
      json: async () => ({}),
      text: async () => "",
    } as unknown as Response;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(emptyRes));

    await expect(removeFromWatchlist("2330")).resolves.toBeUndefined();
  });
});
