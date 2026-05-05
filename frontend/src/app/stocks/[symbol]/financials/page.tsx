"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { LoadingSpinner } from "@/components/ui/loading";
import { ErrorState } from "@/components/ui/empty-state";
import { getErrorMessage } from "@/lib/type-guards";
import { useFinancialAnalysis } from "@/hooks/use-market-data";
import { AmbientBackground } from "@/components/stratos/ambient";
import { OverviewTab } from "./components/OverviewTab";
import { StatementTab } from "./components/StatementTab";

type TabId = "overview" | "income" | "balance" | "cashflow";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "總覽" },
  { id: "income", label: "損益表" },
  { id: "balance", label: "資產負債表" },
  { id: "cashflow", label: "現金流量表" },
];

export default function FinancialsPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const { data, isLoading, error: queryError } = useFinancialAnalysis(symbol);
  const error = queryError ? getErrorMessage(queryError) : null;
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  if (isLoading) return <LoadingSpinner text="載入財務資料中..." fullPage />;
  if (error) return <div className="p-6 max-w-md mx-auto"><ErrorState message={error} /></div>;
  if (!data) return <div className="p-6 text-center text-[var(--text-muted)] text-sm">無資料</div>;

  return (
    <div className="relative flex-1 overflow-y-auto">
      <AmbientBackground />

      {/* Inner Tabs */}
      <div
        style={{
          display: "flex",
          gap: 2,
          padding: "12px 24px 0",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-secondary)",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "6px 18px",
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              border: "none",
              cursor: "pointer",
              background: activeTab === tab.id ? "var(--accent-cyan)" : "transparent",
              color: activeTab === tab.id ? "#09090b" : "var(--text-muted)",
              transition: "all 0.15s",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{ padding: 24 }}>
        {activeTab === "overview" && (
          <OverviewTab ratios={data.ratios} healthScores={data.health_scores} cashFlows={data.financials.cash_flows} />
        )}
        {activeTab === "income" && (
          <StatementTab statements={data.financials.income_statements} type="income" />
        )}
        {activeTab === "balance" && (
          <StatementTab statements={data.financials.balance_sheets} type="balance" />
        )}
        {activeTab === "cashflow" && (
          <StatementTab statements={data.financials.cash_flows} type="cashflow" />
        )}
      </div>
    </div>
  );
}
