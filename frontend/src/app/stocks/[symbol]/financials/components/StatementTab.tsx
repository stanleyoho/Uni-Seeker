"use client";

import type { FinancialStatement } from "@/lib/api-client";
import { GlassPanel } from "@/components/stratos/primitives";

interface StatementTabProps {
  statements: FinancialStatement[];
  type: "income" | "balance" | "cashflow";
}

// 各報表要顯示的科目（yfinance 欄位名稱）
const INCOME_KEYS = [
  "Total Revenue",
  "Gross Profit",
  "Operating Income",
  "Net Income",
  "Basic EPS",
  "EBITDA",
];

const BALANCE_KEYS = [
  "Total Assets",
  "Total Liabilities Net Minority Interest",
  "Stockholders Equity",
  "Cash And Cash Equivalents",
  "Total Debt",
  "Current Assets",
  "Current Liabilities",
];

const CASHFLOW_KEYS = [
  "Operating Cash Flow",
  "Investing Cash Flow",
  "Financing Cash Flow",
  "Free Cash Flow",
  "Capital Expenditure",
];

const KEY_MAP: Record<StatementTabProps["type"], string[]> = {
  income: INCOME_KEYS,
  balance: BALANCE_KEYS,
  cashflow: CASHFLOW_KEYS,
};

const LABEL_MAP: Record<string, string> = {
  "Total Revenue": "營業收入",
  "Gross Profit": "營業毛利",
  "Operating Income": "營業利益",
  "Net Income": "稅後淨利",
  "Basic EPS": "EPS",
  "EBITDA": "EBITDA",
  "Total Assets": "總資產",
  "Total Liabilities Net Minority Interest": "總負債",
  "Stockholders Equity": "股東權益",
  "Cash And Cash Equivalents": "現金及約當現金",
  "Total Debt": "總債務",
  "Current Assets": "流動資產",
  "Current Liabilities": "流動負債",
  "Operating Cash Flow": "營業現金流",
  "Investing Cash Flow": "投資現金流",
  "Financing Cash Flow": "融資現金流",
  "Free Cash Flow": "自由現金流",
  "Capital Expenditure": "資本支出",
};

function fmtVal(v: string | undefined): string {
  if (v === undefined || v === null || v === "") return "—";
  const n = Number(v);
  if (!isFinite(n)) return "—";
  if (Math.abs(n) >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return <span style={{ color: "var(--text-muted)", fontSize: 10 }}>—</span>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const W = 80;
  const H = 28;
  const step = W / (values.length - 1);
  const pts = values
    .map((v, i) => `${i * step},${H - ((v - min) / range) * (H - 4) - 2}`)
    .join(" ");
  const last = values[values.length - 1];
  const prev = values[values.length - 2];
  const color = last >= prev ? "#22c55e" : "#ef4444";
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      <circle
        cx={(values.length - 1) * step}
        cy={H - ((last - min) / range) * (H - 4) - 2}
        r="2.5"
        fill={color}
      />
    </svg>
  );
}

export function StatementTab({ statements, type }: StatementTabProps) {
  if (!statements || statements.length === 0) {
    return (
      <GlassPanel>
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text-muted)" }}>
          暫無報表資料
        </div>
      </GlassPanel>
    );
  }

  // 最近 4 期，最新在左
  const periods = statements.slice(0, 4);
  const keys = KEY_MAP[type];

  return (
    <GlassPanel noPadding>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
              <th style={{ padding: "10px 16px", textAlign: "left", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                科目
              </th>
              {periods.map((s) => (
                <th key={s.period} style={{ padding: "10px 16px", textAlign: "right", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
                  {s.period}
                </th>
              ))}
              <th style={{ padding: "10px 16px", textAlign: "center", fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)" }}>
                趨勢
              </th>
            </tr>
          </thead>
          <tbody>
            {keys.map((key, i) => {
              // sparkline: oldest→newest (reverse of display order)
              const validValues = periods
                .slice()
                .reverse()
                .flatMap((s) => {
                  const raw = s.data[key];
                  if (raw === undefined || raw === "") return [];
                  const n = Number(raw);
                  return isFinite(n) ? [n] : [];
                });

              return (
                <tr
                  key={key}
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)",
                  }}
                >
                  <td style={{ padding: "10px 16px", fontWeight: 700, color: "var(--foreground)" }}>
                    {LABEL_MAP[key] ?? key}
                    <span style={{ display: "block", fontSize: 9, color: "var(--text-muted)", fontWeight: 400, marginTop: 1 }}>
                      {key}
                    </span>
                  </td>
                  {periods.map((s) => {
                    const v = s.data[key];
                    const n = Number(v ?? "");
                    const isNeg = isFinite(n) && n < 0;
                    return (
                      <td key={s.period} style={{ padding: "10px 16px", textAlign: "right", fontVariantNumeric: "tabular-nums", fontFamily: "monospace", color: isNeg ? "var(--stock-down)" : "var(--foreground)" }}>
                        {fmtVal(v)}
                      </td>
                    );
                  })}
                  <td style={{ padding: "10px 16px", textAlign: "center" }}>
                    <Sparkline values={validValues} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </GlassPanel>
  );
}
