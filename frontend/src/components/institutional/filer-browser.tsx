"use client";

/**
 * Filer Browser — inline search + subscribe surface for `/institutional`.
 *
 * Why this exists:
 *   The default `/institutional` view used to be a dead-end empty state
 *   ("尚未訂閱任何機構 / 基金" + a CTA that opened FilerSearchModal). Users
 *   couldn't discover what was browseable without first clicking a button.
 *   This component fixes that by rendering a persistent search box +
 *   browseable list inline, so a first-time user lands on something they
 *   can immediately scan and act on.
 *
 * Behaviour:
 *   - Empty query  → render a 3-row curated teaser (Berkshire / Bridgewater
 *                    / ARK). Backend `searchFilers("")` rejects with 422
 *                    and there is no "top by AUM" endpoint, so a tiny
 *                    hard-coded seed list is the cheapest discoverability
 *                    win. Each teaser row is a regular subscribe target.
 *   - ≥ 2 chars    → debounced `useFilerSearch` (300 ms). Same hook the
 *                    FilerSearchModal uses; cache is shared.
 *
 * Subscription state:
 *   `useInstitutionalFilers()` is read once; we project the subscribed
 *   set into a CIK lookup so each row can switch between
 *   "[+ 訂閱]" and a "已訂閱" chip without a per-row query.
 *
 * Error mapping:
 *   Reuses the same 403/409/502 → zh-TW table as FilerSearchModal. We
 *   intentionally duplicate the mapping (rather than export a helper)
 *   to keep this component's surface area self-contained — the modal
 *   and the inline browser have slightly different error UX requirements
 *   (banner vs row-level chip) and the duplication is tiny.
 */

import { useEffect, useMemo, useState } from "react";
import { ClippedButton, GlassPanel } from "@/components/stratos/primitives";
import {
  useFilerSearch,
  useInstitutionalFilers,
  useSubscribeFiler,
} from "@/hooks/use-institutional";
import { ApiError, type F13FilerSearchResult } from "@/lib/api-client";

/* ------------------------------------------------------------------ */
/*  Curated fallback                                                   */
/* ------------------------------------------------------------------ */

/**
 * 3 hard-coded famous 13F filers — discoverability fallback for the
 * "empty search" case. Backend `searchFilers("")` rejects with 422 and
 * there is no "list by AUM" endpoint as of this PR, so we hand-pick the
 * three most recognisable names from the 13F ecosystem.
 *
 * CIKs were verified against SEC EDGAR on 2026-05-29:
 *   - Berkshire Hathaway Inc        → 0001067983
 *   - Bridgewater Associates, LP    → 0001350694
 *   - ARK Investment Management LLC → 0001697748
 *
 * Stored without leading zeros to match the backend's normalised CIK form
 * (the search endpoint returns CIKs the same way).
 */
const CURATED_FILERS: F13FilerSearchResult[] = [
  {
    cik: "1067983",
    name: "Berkshire Hathaway Inc",
    legal_name: "BERKSHIRE HATHAWAY INC",
    is_locally_known: false,
  },
  {
    cik: "1350694",
    name: "Bridgewater Associates, LP",
    legal_name: "BRIDGEWATER ASSOCIATES, LP",
    is_locally_known: false,
  },
  {
    cik: "1697748",
    name: "ARK Investment Management LLC",
    legal_name: "ARK INVESTMENT MANAGEMENT LLC",
    is_locally_known: false,
  },
];

/* ------------------------------------------------------------------ */
/*  Error mapping                                                      */
/* ------------------------------------------------------------------ */

function mapSubscribeError(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return err instanceof Error ? err.message : "訂閱失敗，請稍後再試";
  }
  const { status, code, message } = err;
  if (status === 403) {
    if (code?.startsWith("limit_exceeded:max_tracked_filers")) {
      return "已達追蹤上限，升級到 Pro";
    }
    if (code?.startsWith("feature_unavailable")) {
      return "升級到 Pro 解鎖此功能";
    }
    return message || "權限不足";
  }
  if (status === 409 || code === "f13_subscription_exists") {
    return "已在追蹤清單";
  }
  if (status === 404) return "找不到對應的 SEC filer";
  if (status === 502) return "SEC EDGAR 暫時無法存取，請稍候重試";
  if (status === 422) return message || "輸入格式錯誤";
  return message || "訂閱失敗";
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none";

export interface FilerBrowserProps {
  /** Called after a successful subscribe (parent may use it to scroll / focus). */
  onSubscribed?: () => void;
}

export function FilerBrowser({ onSubscribed }: FilerBrowserProps) {
  const [rawQuery, setRawQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [pendingCik, setPendingCik] = useState<string | null>(null);

  // 300ms debounce — matches FilerSearchModal so EDGAR rate-limit budget
  // is spent the same way across both entry points.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(rawQuery.trim()), 300);
    return () => clearTimeout(id);
  }, [rawQuery]);

  const { data: searchResults, isFetching, error: searchError } =
    useFilerSearch(debounced);
  const { data: subscribed = [] } = useInstitutionalFilers();
  const subscribe = useSubscribeFiler();

  // Project subscribed filers into a CIK set so per-row lookup is O(1).
  const subscribedCiks = useMemo(
    () => new Set(subscribed.map((f) => f.cik)),
    [subscribed],
  );

  // Curated fallback is only shown when the user hasn't typed anything;
  // the moment they type ≥ 2 chars we hand off to live search.
  const showCurated = debounced.length < 2;
  const rows: F13FilerSearchResult[] = showCurated
    ? CURATED_FILERS
    : (searchResults ?? []);

  async function handleSubscribe(hit: F13FilerSearchResult) {
    setBannerError(null);
    setPendingCik(hit.cik);
    try {
      await subscribe.mutateAsync({ cik: hit.cik, name: hit.name });
      onSubscribed?.();
    } catch (e) {
      setBannerError(mapSubscribeError(e));
    } finally {
      setPendingCik(null);
    }
  }

  return (
    <GlassPanel noPadding>
      <div style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
        {/* Header */}
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h3
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.15em",
              color: "var(--text-muted)",
              textTransform: "uppercase",
              margin: 0,
            }}
          >
            BROWSE 13F FILERS
          </h3>
          <p
            style={{
              fontSize: 12,
              color: "var(--foreground)",
              margin: 0,
            }}
          >
            搜尋並訂閱 SEC EDGAR 13F 申報人，下方未輸入時顯示熱門 filer 範例
          </p>
        </div>

        {/* Search input */}
        <div>
          <label htmlFor="filer-browser-q" className="sr-only">
            搜尋 13F 申報人
          </label>
          <input
            id="filer-browser-q"
            className={inputCls}
            placeholder="搜尋 13F 申報人 (CIK, 名稱)"
            value={rawQuery}
            onChange={(e) => {
              setRawQuery(e.target.value);
              setBannerError(null);
            }}
            aria-label="搜尋 13F 申報人"
          />
          <p
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              marginTop: 6,
            }}
          >
            {showCurated
              ? "輸入至少 2 字元開始 SEC EDGAR 搜尋，目前顯示熱門 13F filer 範例"
              : isFetching
                ? "搜尋中..."
                : `${rows.length} 筆結果`}
          </p>
        </div>

        {/* Banner error */}
        {bannerError && (
          <div
            role="alert"
            style={{
              fontSize: 12,
              color: "#fff",
              background: "var(--accent-primary)",
              padding: "8px 12px",
              fontWeight: 600,
            }}
          >
            {bannerError}
          </div>
        )}

        {/* Search transport error — only shown when live search failed AND
         * we don't already have a banner from a subscribe failure. */}
        {searchError && !bannerError && !showCurated && (
          <div
            role="alert"
            style={{
              fontSize: 12,
              color: "var(--text-muted)",
              background: "var(--bg-secondary)",
              padding: "8px 12px",
            }}
          >
            搜尋暫時無法使用（EDGAR 連線異常），僅顯示本地已知結果
          </div>
        )}

        {/* List */}
        <div
          style={{
            border: "1px solid var(--border-subtle)",
            background: "var(--bg-secondary)",
            maxHeight: 360,
            overflowY: "auto",
          }}
        >
          {rows.length === 0 && !isFetching ? (
            <div
              style={{
                padding: "24px 16px",
                textAlign: "center",
                color: "var(--text-muted)",
                fontSize: 12,
              }}
            >
              查無對應 filer
            </div>
          ) : (
            <ul
              style={{
                listStyle: "none",
                margin: 0,
                padding: 0,
              }}
            >
              {rows.map((hit) => (
                <FilerRow
                  key={hit.cik}
                  hit={hit}
                  subscribed={subscribedCiks.has(hit.cik)}
                  pending={pendingCik === hit.cik && subscribe.isPending}
                  disabled={subscribe.isPending}
                  onSubscribe={() => handleSubscribe(hit)}
                  curated={showCurated}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </GlassPanel>
  );
}

/* ------------------------------------------------------------------ */
/*  Row                                                                */
/* ------------------------------------------------------------------ */

interface FilerRowProps {
  hit: F13FilerSearchResult;
  subscribed: boolean;
  pending: boolean;
  disabled: boolean;
  onSubscribe: () => void;
  curated: boolean;
}

function FilerRow({
  hit,
  subscribed,
  pending,
  disabled,
  onSubscribe,
  curated,
}: FilerRowProps) {
  return (
    <li
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 12px",
        borderBottom: "1px solid var(--border-subtle)",
        gap: 12,
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 4,
          minWidth: 0,
          flex: 1,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontSize: 13,
              fontWeight: 700,
              color: "var(--foreground)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {hit.name}
          </span>
          {hit.is_locally_known && (
            <Badge label="本地已知" tone="cyan" />
          )}
          {curated && !hit.is_locally_known && (
            <Badge label="熱門" tone="muted" />
          )}
        </div>
        <span
          style={{
            fontSize: 10,
            color: "var(--text-muted)",
            fontFamily: "monospace",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          CIK {hit.cik}
          {hit.legal_name && hit.legal_name !== hit.name && (
            <span style={{ marginLeft: 8, fontFamily: "inherit" }}>
              · {hit.legal_name}
            </span>
          )}
        </span>
      </div>

      {subscribed ? (
        <SubscribedChip />
      ) : (
        <ClippedButton
          variant="cyan-ghost"
          size="sm"
          onClick={onSubscribe}
          disabled={disabled}
        >
          {pending ? "訂閱中..." : "+ 訂閱"}
        </ClippedButton>
      )}
    </li>
  );
}

/* ------------------------------------------------------------------ */
/*  Tiny presentational helpers                                        */
/* ------------------------------------------------------------------ */

function Badge({ label, tone }: { label: string; tone: "cyan" | "muted" }) {
  const cyan = tone === "cyan";
  return (
    <span
      style={{
        fontSize: 9,
        fontWeight: 700,
        padding: "2px 6px",
        background: cyan
          ? "color-mix(in srgb, var(--accent-cyan) 16%, transparent)"
          : "var(--bg-secondary)",
        color: cyan ? "var(--accent-cyan)" : "var(--text-muted)",
        border: `1px solid ${cyan ? "var(--accent-cyan)" : "var(--border-subtle)"}`,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {label}
    </span>
  );
}

function SubscribedChip() {
  return (
    <span
      aria-label="已訂閱"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        fontWeight: 700,
        padding: "4px 10px",
        background: "color-mix(in srgb, var(--stock-down) 18%, transparent)",
        color: "var(--stock-down)",
        border: "1px solid var(--stock-down)",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        whiteSpace: "nowrap",
      }}
    >
      <span aria-hidden style={{ fontSize: 12, lineHeight: 1 }}>
        ✓
      </span>
      已訂閱
    </span>
  );
}
