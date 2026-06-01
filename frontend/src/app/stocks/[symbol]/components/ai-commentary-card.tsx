"use client";

/**
 * AiCommentaryCard — "今日 AI 解讀" section on the stock detail page.
 *
 * Renders the deterministic narrative produced by
 * `GET /api/v1/stocks/{symbol}/ai-commentary`. Surfaces:
 *   - the 100-300 字 Chinese narrative paragraph
 *   - a confidence chip when < ~0.7 (hints "data sparse")
 *   - the source breakdown (price / RSI / MACD / etc) collapsed
 *     behind a "依據資料" toggle for transparency
 *
 * Styled with STRATOS GlassPanel to match the rest of the page. We use
 * a serif body font (`var(--font-serif)` if defined) to give the
 * narrative a editorial feel without pulling in a Tailwind `prose`
 * plugin (the project doesn't use it elsewhere).
 */

import React, { useState } from "react";
import { GlassPanel } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import type { AiCommentaryResponse } from "@/lib/api-client";

interface AiCommentaryCardProps {
  data: AiCommentaryResponse | undefined;
  isLoading: boolean;
  isError: boolean;
}

export function AiCommentaryCard({ data, isLoading, isError }: AiCommentaryCardProps) {
  const [showSources, setShowSources] = useState(false);

  return (
    <GlassPanel title="今日 AI 解讀">
      {isLoading && (
        <div className="h-32 flex items-center justify-center" aria-busy="true">
          <LoadingSpinner />
        </div>
      )}

      {!isLoading && (isError || !data) && (
        <div className="py-6 text-center text-[var(--text-muted)] text-sm">
          目前尚無 AI 解讀資料。
        </div>
      )}

      {!isLoading && data && (
        <div>
          {/* Meta strip — date + confidence */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 10,
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--text-muted)",
            }}
          >
            <span>資料日期 · {data.date}</span>
            <ConfidenceChip value={data.confidence} />
          </div>

          {/* The narrative itself. Line-height 1.85 gives the editorial
              feel that aistockmap uses for its commentary blocks. */}
          <p
            style={{
              margin: 0,
              fontSize: 13.5,
              lineHeight: 1.95,
              color: "var(--foreground)",
              fontFamily: "var(--font-serif, var(--font-sans, inherit))",
              textAlign: "justify",
            }}
          >
            {data.commentary}
          </p>

          {/* Sources toggle */}
          {data.sources.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <button
                type="button"
                onClick={() => setShowSources((v) => !v)}
                aria-expanded={showSources}
                style={{
                  background: "transparent",
                  border: "1px solid var(--border-subtle, rgba(255,255,255,0.08))",
                  color: "var(--accent-cyan, #67e8f9)",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  padding: "4px 10px",
                  cursor: "pointer",
                }}
              >
                {showSources ? "收合依據資料" : `展開依據資料 (${data.sources.length})`}
              </button>
              {showSources && (
                <ul
                  style={{
                    marginTop: 10,
                    padding: 0,
                    listStyle: "none",
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                    gap: 6,
                  }}
                >
                  {data.sources.map((s) => (
                    <li
                      key={`${s.kind}-${s.detail}`}
                      style={{
                        fontSize: 11,
                        color: "var(--text-secondary)",
                        padding: "4px 8px",
                        background: "var(--bg-secondary, rgba(255,255,255,0.03))",
                        border: "1px solid var(--border-subtle, rgba(255,255,255,0.06))",
                        fontFamily: "var(--font-mono, monospace)",
                      }}
                    >
                      <span
                        style={{
                          display: "inline-block",
                          marginRight: 6,
                          fontSize: 9,
                          fontWeight: 700,
                          textTransform: "uppercase",
                          color: "var(--text-muted)",
                          letterSpacing: "0.08em",
                        }}
                      >
                        {s.kind}
                      </span>
                      {s.detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Disclaimer line. AI commentary is templated facts — not
              investment advice — and we say so plainly. */}
          <p
            style={{
              marginTop: 12,
              marginBottom: 0,
              fontSize: 10,
              color: "var(--text-muted)",
              letterSpacing: "0.04em",
            }}
          >
            ※ 本文由系統根據量價與技術指標自動生成，僅供研究參考，非投資建議。
          </p>
        </div>
      )}
    </GlassPanel>
  );
}

function ConfidenceChip({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  // <0.5 → red-ish (sparse), 0.5-0.8 → amber, >=0.8 → green
  let color = "var(--stock-up, #10b981)";
  let label = "資料充足";
  if (value < 0.5) {
    color = "var(--stock-down, #ef4444)";
    label = "資料稀疏";
  } else if (value < 0.8) {
    color = "var(--accent-cyan, #f59e0b)";
    label = "資料尚可";
  }
  return (
    <span
      title={`AI 信心度 ${pct}%`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 6px",
        border: `1px solid ${color}`,
        color,
        fontSize: 9,
        fontWeight: 700,
        letterSpacing: "0.08em",
      }}
    >
      <span style={{ width: 5, height: 5, borderRadius: 999, background: color }} />
      信心 {pct}% · {label}
    </span>
  );
}
