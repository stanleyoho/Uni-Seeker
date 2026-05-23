"use client";

/**
 * Filer Search Modal — typeahead search + one-click subscribe.
 *
 * Flow:
 *   1. User types ≥ 2 chars → `useFilerSearch` debounced 300ms.
 *   2. Results render with an `is_locally_known` badge (a filer we've seen
 *      before) vs an EDGAR-only hit (we'll create the row on subscribe).
 *   3. Click "訂閱" → `useSubscribeFiler.mutate({ cik, name })`.
 *   4. Backend errors are mapped to zh-TW labels:
 *        - 403 limit_exceeded:max_tracked_filers → "已達追蹤上限，升級到 Pro"
 *        - 409 f13_subscription_exists           → "已在追蹤清單"
 *      Anything else surfaces the raw `message`.
 *
 * Closing the modal on backdrop click is suppressed while a subscribe is
 * in flight to prevent orphaned mutations from racing the unmount.
 */

import { useEffect, useState } from "react";
import { ClippedButton } from "@/components/stratos/primitives";
import {
  useFilerSearch,
  useSubscribeFiler,
} from "@/hooks/use-institutional";
import { ApiError, type F13FilerSearchResult } from "@/lib/api-client";

interface FilerSearchModalProps {
  onClose: () => void;
  /** Called after a successful subscribe so the parent can refresh state. */
  onSubscribed?: () => void;
}

const inputCls =
  "w-full px-3 py-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)] text-sm text-[var(--foreground)] placeholder-[var(--text-muted)] focus:border-[var(--accent-cyan)] outline-none";

const labelCls =
  "text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-1 block";

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

export function FilerSearchModal({
  onClose,
  onSubscribed,
}: FilerSearchModalProps) {
  const [rawQuery, setRawQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [bannerError, setBannerError] = useState<string | null>(null);
  const [pendingCik, setPendingCik] = useState<string | null>(null);

  // 300ms debounce — matches the perceived "I stopped typing" threshold
  // and keeps EDGAR rate-limit budget intact during fast keystrokes.
  useEffect(() => {
    const id = setTimeout(() => setDebounced(rawQuery.trim()), 300);
    return () => clearTimeout(id);
  }, [rawQuery]);

  const { data: results, isFetching, error: searchError } =
    useFilerSearch(debounced);
  const subscribe = useSubscribeFiler();

  async function handleSubscribe(hit: F13FilerSearchResult) {
    setBannerError(null);
    setPendingCik(hit.cik);
    try {
      await subscribe.mutateAsync({ cik: hit.cik, name: hit.name });
      onSubscribed?.();
      onClose();
    } catch (e) {
      setBannerError(mapSubscribeError(e));
    } finally {
      setPendingCik(null);
    }
  }

  const isPending = subscribe.isPending;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(4px)",
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
      onClick={(e) => e.target === e.currentTarget && !isPending && onClose()}
    >
      <div
        className="p-4 sm:p-6"
        style={{
          background: "var(--glass-bg)",
          border: "1px solid var(--border-color)",
          width: "100%",
          maxWidth: 560,
          maxHeight: "calc(100vh - 32px)",
          display: "flex",
          flexDirection: "column",
          boxShadow: "var(--glass-shadow)",
          backgroundImage: "var(--glass-gradient)",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: 20,
          }}
        >
          <span
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: "var(--foreground)",
              letterSpacing: "-0.04em",
              textTransform: "uppercase",
            }}
          >
            訂閱機構 / 基金
          </span>
          <button
            onClick={onClose}
            disabled={isPending}
            aria-label="關閉"
            style={{
              color: "var(--text-muted)",
              background: "none",
              border: "none",
              cursor: isPending ? "not-allowed" : "pointer",
              fontSize: 20,
              lineHeight: 1,
              padding: 4,
            }}
          >
            ×
          </button>
        </div>

        {/* Search input */}
        <div>
          <label className={labelCls}>SEC EDGAR 名稱 / CIK</label>
          <input
            className={inputCls}
            placeholder="例：Berkshire Hathaway, ARK Invest, Situational Awareness"
            value={rawQuery}
            onChange={(e) => {
              setRawQuery(e.target.value);
              setBannerError(null);
            }}
            autoFocus
            disabled={isPending}
          />
          <p
            style={{
              fontSize: 10,
              color: "var(--text-muted)",
              marginTop: 6,
            }}
          >
            {rawQuery.trim().length < 2
              ? "輸入至少 2 字元開始搜尋（含本地已知 + SEC EDGAR）"
              : isFetching
                ? "搜尋中..."
                : `${results?.length ?? 0} 筆結果`}
          </p>
        </div>

        {/* Banner error */}
        {bannerError && (
          <div
            role="alert"
            style={{
              marginTop: 12,
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

        {searchError && !bannerError && (
          <div
            role="alert"
            style={{
              marginTop: 12,
              fontSize: 12,
              color: "var(--text-muted)",
              background: "var(--bg-secondary)",
              padding: "8px 12px",
            }}
          >
            搜尋暫時無法使用（EDGAR 連線異常），僅顯示本地已知結果
          </div>
        )}

        {/* Results */}
        <div
          style={{
            marginTop: 16,
            overflowY: "auto",
            flex: 1,
            border: "1px solid var(--border-subtle)",
            background: "var(--bg-secondary)",
          }}
        >
          {(results ?? []).length === 0 && debounced.length >= 2 && !isFetching ? (
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
              {(results ?? []).map((hit) => {
                const rowPending = pendingCik === hit.cik && isPending;
                return (
                  <li
                    key={hit.cik}
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
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
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
                          <span
                            style={{
                              fontSize: 9,
                              fontWeight: 700,
                              padding: "2px 6px",
                              background:
                                "color-mix(in srgb, var(--accent-cyan) 16%, transparent)",
                              color: "var(--accent-cyan)",
                              border: "1px solid var(--accent-cyan)",
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                            }}
                          >
                            本地已知
                          </span>
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

                    <ClippedButton
                      variant="cyan-ghost"
                      size="sm"
                      onClick={() => handleSubscribe(hit)}
                      disabled={isPending}
                    >
                      {rowPending ? "訂閱中..." : "訂閱"}
                    </ClippedButton>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer close */}
        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
          <ClippedButton
            variant="white-solid"
            size="md"
            onClick={onClose}
            disabled={isPending}
          >
            關閉
          </ClippedButton>
        </div>
      </div>
    </div>
  );
}
