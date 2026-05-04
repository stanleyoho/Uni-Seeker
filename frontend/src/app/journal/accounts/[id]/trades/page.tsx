"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { AmbientBackground } from "@/components/stratos/ambient";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { useJournalTrades, useJournalAccounts } from "@/hooks/use-journal";
import { AddTradeModal } from "@/components/journal/add-trade-modal";

const ACTION_COLOR: Record<string, string> = {
  BUY: "var(--stock-up)",
  SELL: "var(--stock-down)",
  DIVIDEND: "#f59e0b",
  SPLIT: "var(--accent-cyan)",
};

function fmt(n: number, dec = 2) {
  return n.toLocaleString("zh-TW", { maximumFractionDigits: dec });
}

export default function TradesPage() {
  const { id } = useParams<{ id: string }>();
  const accountId = Number(id) || 0;
  const [page, setPage] = useState(1);
  const [showModal, setShowModal] = useState(false);
  const { data = { total: 0, items: [] }, isLoading } = useJournalTrades(accountId, { page, page_size: 50 });
  const { data: accounts = [] } = useJournalAccounts();

  const totalPages = Math.ceil(data.total / 50);

  return (
    <div className="relative flex-1 overflow-y-auto p-6 space-y-4">
      <AmbientBackground />

      <GlassPanel title="交易記錄" noPadding>
        <div style={{ padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border-subtle)" }}>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>共 {data.total} 筆記錄</span>
          <ClippedButton variant="green-solid" size="sm" onClick={() => setShowModal(true)}>
            + 新增交易
          </ClippedButton>
        </div>

        {isLoading ? (
          <div style={{ padding: 20, color: "var(--text-muted)", fontSize: 13 }}>載入中...</div>
        ) : data.items.length === 0 ? (
          <div style={{ padding: 20, color: "var(--text-muted)", fontSize: 13 }}>尚無交易記錄</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  {["日期", "動作", "標的", "價格", "數量", "手續費", "稅", "備註"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "8px 12px",
                        textAlign: h === "日期" || h === "動作" || h === "標的" || h === "備註" ? "left" : "right",
                        color: "var(--text-muted)",
                        fontWeight: 700,
                        fontSize: 10,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.items.map((trade, i) => (
                  <tr
                    key={trade.id}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)",
                    }}
                  >
                    <td style={{ padding: "9px 12px", color: "var(--text-muted)" }}>{trade.date}</td>
                    <td style={{ padding: "9px 12px" }}>
                      <span style={{ color: ACTION_COLOR[trade.action] ?? "var(--foreground)", fontWeight: 700 }}>
                        {trade.action}
                      </span>
                    </td>
                    <td style={{ padding: "9px 12px", fontWeight: 700, color: "var(--foreground)" }}>
                      {trade.symbol}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                      {trade.price ? fmt(Number(trade.price), 4) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace" }}>
                      {trade.quantity ? fmt(Number(trade.quantity), 4) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                      {Number(trade.fee) > 0 ? fmt(Number(trade.fee)) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", textAlign: "right", fontFamily: "monospace", color: "var(--text-muted)" }}>
                      {Number(trade.tax) > 0 ? fmt(Number(trade.tax)) : "—"}
                    </td>
                    <td style={{ padding: "9px 12px", color: "var(--text-muted)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {trade.note ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{ padding: "12px 16px", display: "flex", gap: 8, justifyContent: "center" }}>
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>
              ← 上一頁
            </ClippedButton>
            <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
              {page} / {totalPages}
            </span>
            <ClippedButton variant="cyan-ghost" size="sm" onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>
              下一頁 →
            </ClippedButton>
          </div>
        )}
      </GlassPanel>

      {showModal && (
        <AddTradeModal
          accounts={accounts}
          defaultAccountId={accountId}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
