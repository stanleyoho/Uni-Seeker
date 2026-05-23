"use client";

/**
 * Institutional 13F Page — Phase 2 + Round 11 advanced views.
 *
 * Round 11 adds a view-switcher toolbar layered over the original Y1 page:
 *
 *   - HOLDINGS   (default)  → original snapshot + QoQ diff (Y1 behaviour)
 *   - TIMELINE              → per-stock multi-quarter shares/value trail
 *                              for a single filer (HoldingsTimeline)
 *   - TOP MOVERS            → ranked buys/sells across one QoQ window
 *                              (TopMovers)
 *   - COMPARE    (modal)    → side-by-side N-filer matrix
 *                              (MultiFilerCompareModal)
 *
 * Tab state lives in `view`. The "compare" action is a modal trigger, not
 * a view — opening it doesn't unmount the underlying page. The timeline
 * view requires a symbol selection; clicking a row in the holdings table
 * sets `selectedSymbol` and the page auto-switches to the timeline view.
 *
 * The original Y1 paths (selectedFilerId, selectedPeriod, diffFromDate/
 * diffToDate) remain authoritative; new views consume those same values
 * so navigation stays cheap (cached React-Query keys are reused).
 */

import { useEffect, useMemo, useState } from "react";
import { AmbientBackground } from "@/components/stratos/ambient";
import {
  ClippedButton,
  GlassPanel,
} from "@/components/stratos/primitives";
import {
  BulkSubscribeModal,
  DiffView,
  FilerList,
  FilerSearchModal,
  HoldingsTimeline,
  InstitutionalHoldingsTable,
  MultiFilerCompareModal,
  RefreshButton,
  TopMovers,
  holdingDisplaySymbol,
  type F13Holding,
} from "@/components/institutional";
import {
  useFilings,
  useHoldings,
  useInstitutionalFilers,
} from "@/hooks/use-institutional";
import { useI18n } from "@/i18n/context";

type ViewMode = "holdings" | "timeline" | "top_movers";

export default function InstitutionalPage() {
  const { t } = useI18n();
  const f13 = t.institutional_13f ?? {};
  const viewsLabels = f13.views ?? {};

  /* --------------------------- State --------------------------- */
  const [selectedFilerId, setSelectedFilerId] = useState<number | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<string>("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [view, setView] = useState<ViewMode>("holdings");
  const [selectedSymbol, setSelectedSymbol] = useState<string>("");

  /* --------------------------- Data --------------------------- */
  const { data: filers = [], isLoading: filersLoading } =
    useInstitutionalFilers();
  const { data: filings = [] } = useFilings(selectedFilerId);
  const { data: holdingsRes, isLoading: holdingsLoading } = useHoldings(
    selectedFilerId,
    selectedPeriod,
  );

  /* Auto-select the first filer once the list resolves. */
  useEffect(() => {
    if (selectedFilerId == null && filers.length > 0) {
      setSelectedFilerId(filers[0].id);
    }
  }, [filers, selectedFilerId]);

  /* Default period to the latest filing once we know the list. */
  useEffect(() => {
    if (filings.length > 0 && !selectedPeriod) {
      setSelectedPeriod(filings[0].report_period_end);
    }
  }, [filings, selectedPeriod]);

  /* Reset period + symbol whenever the filer changes. */
  useEffect(() => {
    setSelectedPeriod("");
    setSelectedSymbol("");
  }, [selectedFilerId]);

  /* Diff defaults to (1 quarter ago, current). */
  const [diffFromDate, diffToDate] = useMemo<[string, string]>(() => {
    if (filings.length < 2) return ["", ""];
    return [filings[1].report_period_end, filings[0].report_period_end];
  }, [filings]);

  const titleLabel = f13.title ?? "機構持倉追蹤 (13F)";
  const subscribeLabel = f13.actions?.subscribe ?? "+ 訂閱機構/基金";

  /* Click a holding row → switch to timeline pinned to that symbol. */
  const handleHoldingClick = (h: F13Holding) => {
    setSelectedSymbol(holdingDisplaySymbol(h));
    setView("timeline");
  };

  /* --------------------------- Render --------------------------- */
  return (
    <main
      className="relative flex-1 overflow-y-auto"
      style={{ background: "var(--background)" }}
    >
      <AmbientBackground />

      <div className="relative max-w-[1440px] mx-auto px-3 sm:px-4 lg:px-6 py-4 lg:py-6 space-y-4 lg:space-y-6">
        {/* Page header */}
        <div
          className="flex flex-col sm:flex-row sm:items-end sm:justify-between"
          style={{
            flexWrap: "wrap",
            gap: 16,
            borderBottom: "1px solid var(--border-subtle)",
            paddingBottom: 16,
          }}
        >
          <div>
            <h1
              className="text-[20px] lg:text-[28px]"
              style={{
                fontWeight: 700,
                color: "var(--foreground)",
                letterSpacing: "-0.04em",
                textTransform: "uppercase",
                margin: 0,
              }}
            >
              {titleLabel}
            </h1>
            <p
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: "var(--text-muted)",
                letterSpacing: "0.15em",
                marginTop: 4,
                textTransform: "uppercase",
              }}
            >
              SEC 13F-HR · QUARTERLY HOLDINGS &amp; QOQ DIFF
            </p>
          </div>
          <div className="grid grid-cols-2 sm:flex gap-2">
            <ClippedButton
              variant="cyan-ghost"
              size="md"
              onClick={() => setBulkOpen(true)}
            >
              批次訂閱
            </ClippedButton>
            <ClippedButton
              variant="red-solid"
              size="md"
              onClick={() => setSearchOpen(true)}
            >
              {subscribeLabel}
            </ClippedButton>
          </div>
        </div>

        {/* Filer list */}
        <section>
          <FilerList
            filers={filers}
            selectedFilerId={selectedFilerId}
            onSelect={setSelectedFilerId}
            loading={filersLoading}
            emptyCta={
              <ClippedButton
                variant="cyan-ghost"
                size="md"
                onClick={() => setSearchOpen(true)}
              >
                {subscribeLabel}
              </ClippedButton>
            }
          />
        </section>

        {/* Detail panes (visible only when a filer is selected) */}
        {selectedFilerId != null && (
          <>
            {/* View toolbar */}
            <section
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 8,
              }}
            >
              <ViewTab
                active={view === "holdings"}
                label={viewsLabels.holdings ?? "Holdings"}
                onClick={() => setView("holdings")}
              />
              <ViewTab
                active={view === "timeline"}
                label={viewsLabels.holdings_timeline ?? "Timeline"}
                onClick={() => setView("timeline")}
                disabled={!selectedSymbol}
                hint={!selectedSymbol ? "點 Holdings 表內任一筆以鎖定 symbol" : undefined}
              />
              <ViewTab
                active={view === "top_movers"}
                label={viewsLabels.top_movers ?? "Top Movers"}
                onClick={() => setView("top_movers")}
              />
              <ClippedButton
                variant="cyan-ghost"
                size="sm"
                onClick={() => setCompareOpen(true)}
              >
                {viewsLabels.multi_filer_compare ?? "Compare"}
              </ClippedButton>

              <div style={{ marginLeft: "auto", display: "flex", gap: 12, alignItems: "center" }}>
                {view === "holdings" && (
                  <PeriodSelector
                    filings={filings}
                    value={selectedPeriod}
                    onChange={setSelectedPeriod}
                  />
                )}
                <RefreshButton filerId={selectedFilerId} />
              </div>
            </section>

            {/* Body — driven by `view` */}
            {view === "holdings" && (
              <>
                <section>
                  <SectionHeading
                    label="HOLDINGS SNAPSHOT"
                    meta={
                      holdingsRes?.filing.report_period_end
                        ? `Period ending ${holdingsRes.filing.report_period_end}`
                        : undefined
                    }
                  />
                  <InstitutionalHoldingsTable
                    holdings={holdingsRes?.holdings ?? []}
                    loading={holdingsLoading}
                    onRowClick={handleHoldingClick}
                  />
                </section>

                <section>
                  <SectionHeading
                    label="QUARTER-OVER-QUARTER MOVES"
                    meta={
                      diffFromDate && diffToDate
                        ? `${diffFromDate} → ${diffToDate}`
                        : "需至少兩個季度的 filing"
                    }
                  />
                  {diffFromDate && diffToDate ? (
                    <DiffView
                      filerId={selectedFilerId}
                      fromDate={diffFromDate}
                      toDate={diffToDate}
                    />
                  ) : (
                    <GlassPanel>
                      <p
                        style={{
                          fontSize: 12,
                          color: "var(--text-muted)",
                          textAlign: "center",
                          padding: "20px 0",
                        }}
                      >
                        觸發 refresh 拉至少 2 個季度的 filing 即可顯示異動
                      </p>
                    </GlassPanel>
                  )}
                </section>
              </>
            )}

            {view === "timeline" && (
              <section>
                <SectionHeading
                  label="HOLDINGS TIMELINE"
                  meta={selectedSymbol ? `Tracking ${selectedSymbol}` : "未選擇 symbol"}
                />
                {selectedSymbol ? (
                  <HoldingsTimeline
                    filerId={selectedFilerId}
                    symbolOrCusip={selectedSymbol}
                  />
                ) : (
                  <GlassPanel>
                    <p
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        textAlign: "center",
                        padding: "20px 0",
                      }}
                    >
                      請回到 Holdings 點選一筆持倉
                    </p>
                  </GlassPanel>
                )}
              </section>
            )}

            {view === "top_movers" && (
              <section>
                <SectionHeading
                  label="TOP MOVERS"
                  meta={
                    diffFromDate && diffToDate
                      ? `${diffFromDate} → ${diffToDate}`
                      : "需至少兩個季度的 filing"
                  }
                />
                {diffFromDate && diffToDate ? (
                  <TopMovers
                    filerId={selectedFilerId}
                    fromDate={diffFromDate}
                    toDate={diffToDate}
                    limit={10}
                  />
                ) : (
                  <GlassPanel>
                    <p
                      style={{
                        fontSize: 12,
                        color: "var(--text-muted)",
                        textAlign: "center",
                        padding: "20px 0",
                      }}
                    >
                      觸發 refresh 拉至少 2 個季度的 filing 即可顯示 movers
                    </p>
                  </GlassPanel>
                )}
              </section>
            )}
          </>
        )}
      </div>

      {/* Modals */}
      {searchOpen && (
        <FilerSearchModal
          onClose={() => setSearchOpen(false)}
          onSubscribed={() => {
            /* React-Query handles cache invalidation. */
          }}
        />
      )}
      {bulkOpen && (
        <BulkSubscribeModal
          onClose={() => setBulkOpen(false)}
          onSuccess={() => {
            /* React-Query handles cache invalidation. */
          }}
        />
      )}
      {compareOpen && (
        <MultiFilerCompareModal
          preselectedFilerIds={selectedFilerId != null ? [selectedFilerId] : []}
          onClose={() => setCompareOpen(false)}
        />
      )}
    </main>
  );
}

/* ------------------------------------------------------------------ */
/*  View tab button                                                    */
/* ------------------------------------------------------------------ */

interface ViewTabProps {
  active: boolean;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  hint?: string;
}

function ViewTab({ active, label, onClick, disabled, hint }: ViewTabProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={hint}
      style={{
        padding: "8px 14px",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        background: active ? "var(--accent-cyan)" : "transparent",
        color: active
          ? "#000"
          : disabled
            ? "var(--text-muted)"
            : "var(--accent-cyan)",
        border: `1px solid ${disabled ? "var(--border-subtle)" : "var(--accent-cyan)"}`,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "background 0.12s, color 0.12s",
      }}
    >
      {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Period selector — narrow <select> built off `useFilings`           */
/* ------------------------------------------------------------------ */

interface PeriodSelectorProps {
  filings: { id: number; report_period_end: string; form_type: string }[];
  value: string;
  onChange: (period: string) => void;
}

function PeriodSelector({ filings, value, onChange }: PeriodSelectorProps) {
  if (filings.length === 0) {
    return (
      <div
        style={{
          fontSize: 11,
          color: "var(--text-muted)",
          padding: "8px 12px",
          border: "1px dashed var(--border-subtle)",
        }}
      >
        無 filing 資料 — 點 Refresh 拉取
      </div>
    );
  }
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.1em",
          color: "var(--text-muted)",
          textTransform: "uppercase",
        }}
      >
        Period
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: "6px 10px",
          background: "var(--bg-secondary)",
          border: "1px solid var(--border-subtle)",
          color: "var(--foreground)",
          fontSize: 12,
          fontFamily: "monospace",
          fontVariantNumeric: "tabular-nums",
          minWidth: 160,
        }}
      >
        {filings.map((f) => (
          <option key={f.id} value={f.report_period_end}>
            {f.report_period_end} · {f.form_type}
          </option>
        ))}
      </select>
    </label>
  );
}

/* ------------------------------------------------------------------ */
/*  Section heading                                                    */
/* ------------------------------------------------------------------ */

function SectionHeading({ label, meta }: { label: string; meta?: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        justifyContent: "space-between",
        marginBottom: 8,
      }}
    >
      <h2
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: "0.15em",
          color: "var(--text-muted)",
          textTransform: "uppercase",
          margin: 0,
        }}
      >
        {label}
      </h2>
      {meta && (
        <span
          style={{
            fontSize: 11,
            color: "var(--text-muted)",
            fontFamily: "monospace",
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {meta}
        </span>
      )}
    </div>
  );
}
