"use client";

// ---------------------------------------------------------------------------
// DslTabPanel — composable Query DSL filter builder (A2).
//
// Mounted by `/research/page.tsx` when `?tab=dsl` is present, alongside the
// Scan / Compare / Best-Four-Point tabs (same `?tab=` query-multiplex
// pattern). Builds an arbitrarily-nested AND/OR filter tree and runs it
// against `POST /screener/dsl`, reusing the screener engine on the backend.
//
// The recursive builder UI lives in
// `@/components/screener/dsl-filter-builder` (pure, prop-driven, RTL-
// testable); this panel owns data-fetching (field metadata + run) and the
// results surface only.
// ---------------------------------------------------------------------------

import { useEffect, useState } from "react";
import { GlassPanel, ClippedButton } from "@/components/stratos/primitives";
import { LoadingSpinner } from "@/components/ui/loading";
import { ResultsTable } from "@/components/screener/results-table";
import {
  fetchDslFields,
  screenDsl,
  type DslFieldMeta,
  type ScreenResponse,
} from "@/lib/api-client";
import {
  DslFilterBuilder,
  builderToFilter,
  countClauses,
  makeClause,
  makeGroup,
  type BuilderGroup,
} from "@/components/screener/dsl-filter-builder";

function initialGroup(defaultField: string): BuilderGroup {
  const g = makeGroup("and");
  g.children = [makeClause(defaultField)];
  return g;
}

export function DslTabPanel() {
  const [fields, setFields] = useState<DslFieldMeta[]>([]);
  const [group, setGroup] = useState<BuilderGroup>(() => initialGroup("RSI"));
  const [result, setResult] = useState<ScreenResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchDslFields()
      .then((res) => {
        if (cancelled) return;
        setFields(res.fields);
        // Re-seed the first clause with a real field key once metadata loads.
        const first = res.fields[0]?.key;
        if (first) {
          setGroup((prev) =>
            prev.children.length === 1 && prev.children[0].kind === "clause"
              ? initialGroup(first)
              : prev,
          );
        }
      })
      .catch(() => {
        if (!cancelled) setError("Failed to load field metadata.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const clauseCount = countClauses(group);

  const handleRun = () => {
    setRunning(true);
    setError(null);
    screenDsl(builderToFilter(group), { limit: 50 })
      .then((res) => setResult(res))
      .catch((e) => setError(e instanceof Error ? e.message : "Screen failed."))
      .finally(() => setRunning(false));
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <div className="lg:col-span-5 space-y-4">
        <GlassPanel title="QUERY DSL FILTER">
          <h4 className="text-[10px] font-bold uppercase tracking-[0.1em] text-[var(--text-muted)] mb-3">
            Compose AND / OR groups of conditions
          </h4>

          <DslFilterBuilder group={group} onChange={setGroup} fields={fields} />

          <div className="mt-5 pt-4 border-t border-[var(--border-subtle)] space-y-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
              {clauseCount} 個條件
            </p>
            <ClippedButton
              variant="red-solid"
              size="md"
              onClick={handleRun}
              disabled={running || clauseCount === 0}
              className="w-full"
            >
              {running ? "RUNNING QUERY..." : "RUN DSL QUERY"}
            </ClippedButton>
          </div>
        </GlassPanel>
      </div>

      <div className="lg:col-span-7">
        <GlassPanel
          title={result ? `RESULTS [${result.total}]` : "ENGINE STANDBY"}
          noPadding
        >
          <div className="min-h-[600px] flex flex-col">
            {running ? (
              <div className="flex-1 flex items-center justify-center">
                <LoadingSpinner />
              </div>
            ) : error ? (
              <div className="flex-1 flex flex-col items-center justify-center p-12 text-center">
                <p className="text-red-400 font-bold text-sm mb-4 uppercase tracking-widest">
                  {error}
                </p>
                <ClippedButton variant="red-ghost" size="sm" onClick={handleRun}>
                  RETRY
                </ClippedButton>
              </div>
            ) : !result ? (
              <div className="flex-1 flex flex-col items-center justify-center p-12 text-center opacity-30">
                <p className="text-xs font-bold uppercase tracking-[0.2em]">
                  Compose a filter and run
                </p>
              </div>
            ) : (
              <div className="p-4">
                <ResultsTable results={result.results} total={result.total} />
              </div>
            )}
          </div>
        </GlassPanel>
      </div>
    </div>
  );
}
