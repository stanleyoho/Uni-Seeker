"use client";

/**
 * Institutional 13F Page — Phase 2 frontend assembly.
 *
 * Composes:
 *   - `useInstitutionalFilers` (X1 hook)             → filer list
 *   - `useFilings(filerId)`                          → period picker
 *   - `useHoldings(filerId, period)`                 → snapshot table
 *   - <FilerList />, <InstitutionalHoldingsTable />, <DiffView />,
 *     <RefreshButton />, <FilerSearchModal />        (X2 components)
 *
 * Selection flow:
 *   1. List loads → first row auto-selected once available (keeps the
 *      page non-empty for newcomers without forcing them to click).
 *   2. Selected filer → fetch filings → period picker materialises with
 *      the latest filing pre-selected.
 *   3. Diff view defaults to (filings[1].period, filings[0].period) once
 *      we have at least two filings; before that, it renders the
 *      "select periods" stub.
 *
 * The legacy Taiwan-stock 三大法人 page lives under
 * `/institutional/daily-flows` (renamed; no behaviour change).
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
  InstitutionalHoldingsTable,
  RefreshButton,
} from "@/components/institutional";
import {
  useFilings,
  useHoldings,
  useInstitutionalFilers,
} from "@/hooks/use-institutional";
import { useI18n } from "@/i18n/context";

export default function InstitutionalPage() {
  const { t } = useI18n();
  const f13 = t.institutional_13f ?? {};

  /* --------------------------- State --------------------------- */
  const [selectedFilerId, setSelectedFilerId] = useState<number | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<string>("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);

  /* --------------------------- Data --------------------------- */
  const { data: filers = [], isLoading: filersLoading } =
    useInstitutionalFilers();
  const { data: filings = [] } = useFilings(selectedFilerId);
  const { data: holdingsRes, isLoading: holdingsLoading } = useHoldings(
    selectedFilerId,
    selectedPeriod,
  );

  /* Auto-select the first filer once the list resolves. We only do this
   * when the user has no current selection; this lets the user clear &
   * pick something else (or stay on the empty state) without the UI
   * snapping back. */
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

  /* Reset period whenever the filer changes. */
  useEffect(() => {
    setSelectedPeriod("");
  }, [selectedFilerId]);

  /* Diff defaults to (1 quarter ago, current). */
  const [diffFromDate, diffToDate] = useMemo<[string, string]>(() => {
    if (filings.length < 2) return ["", ""];
    return [filings[1].report_period_end, filings[0].report_period_end];
  }, [filings]);

  const titleLabel = f13.title ?? "機構持倉追蹤 (13F)";
  const subscribeLabel = f13.actions?.subscribe ?? "+ 訂閱機構/基金";

  /* --------------------------- Render --------------------------- */
  return (
    <main
      className="relative flex-1 overflow-y-auto"
      style={{ background: "var(--background)" }}
    >
      <AmbientBackground />

      <div className="relative max-w-[1440px] mx-auto px-6 py-6 space-y-6">
        {/* Page header */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 16,
            borderBottom: "1px solid var(--border-subtle)",
            paddingBottom: 16,
          }}
        >
          <div>
            <h1
              style={{
                fontSize: 28,
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
          <div style={{ display: "flex", gap: 8 }}>
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
            {/* Period selector + refresh */}
            <section
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 12,
              }}
            >
              <PeriodSelector
                filings={filings}
                value={selectedPeriod}
                onChange={setSelectedPeriod}
              />
              <RefreshButton filerId={selectedFilerId} />
            </section>

            {/* Holdings table */}
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
              />
            </section>

            {/* Diff view */}
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
      </div>

      {/* Modal */}
      {searchOpen && (
        <FilerSearchModal
          onClose={() => setSearchOpen(false)}
          onSubscribed={() => {
            /* React-Query handles cache invalidation. We could optionally
             * auto-select the new filer once the list refetches; deferred
             * because we don't have the resolved filer_id at this point.
             */
          }}
        />
      )}
      {bulkOpen && (
        <BulkSubscribeModal
          onClose={() => setBulkOpen(false)}
          onSuccess={() => {
            /* React-Query invalidates filers.all on success; the list
             * refetch surfaces the new rows. The modal stays open if
             * there were errors/duplicates so the user can review.
             */
          }}
        />
      )}
    </main>
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
