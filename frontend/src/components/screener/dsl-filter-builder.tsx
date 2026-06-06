"use client";

import type { DslClause, DslFieldMeta, DslGroup } from "@/lib/api-client";

// Comparators surfaced in the UI. Mirrors the backend's `cmp` allowlist
// (`app.modules.screener.dsl.CMP_TO_OP`). "between" is intentionally
// omitted from the v1 builder — it needs a two-value input that doesn't
// fit the single-number row; the API still accepts it for power users.
export const DSL_BUILDER_COMPARATORS: { value: DslClause["cmp"]; label: string }[] = [
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "eq", label: "==" },
];

// ---- Pure builder state model (exported for unit/RTL tests) --------------
//
// The builder works on a discriminated tree mirroring the API's
// `DslGroup` / `DslClause` shape. We keep an internal model identical to
// the wire shape so `buildState -> payload` is the identity for groups and
// a trivial map for clauses — no impedance mismatch, no hidden transform
// where bugs hide.

export type BuilderNode = BuilderClause | BuilderGroup;

export interface BuilderClause {
  kind: "clause";
  field: string;
  cmp: DslClause["cmp"];
  value: number;
}

export interface BuilderGroup {
  kind: "group";
  op: "and" | "or";
  children: BuilderNode[];
}

export function makeClause(field: string): BuilderClause {
  return { kind: "clause", field, cmp: "lt", value: 0 };
}

export function makeGroup(op: "and" | "or" = "and"): BuilderGroup {
  return { kind: "group", op, children: [] };
}

/**
 * Convert the builder tree into the API `DslGroup` payload.
 *
 * Exported so it can be unit/RTL-tested without rendering: the contract is
 * "what the builder shows == what gets sent". A group with zero children is
 * preserved as-is; the caller (or the backend's StrictModel/`min_length=1`)
 * is responsible for rejecting empty groups.
 */
export function builderToFilter(group: BuilderGroup): DslGroup {
  return {
    op: group.op,
    clauses: group.children.map((child) =>
      child.kind === "group"
        ? builderToFilter(child)
        : ({ field: child.field, cmp: child.cmp, value: child.value } satisfies DslClause),
    ),
  };
}

/** Total leaf-clause count anywhere in the tree (UI summary / validation). */
export function countClauses(group: BuilderGroup): number {
  return group.children.reduce(
    (n, child) => n + (child.kind === "group" ? countClauses(child) : 1),
    0,
  );
}

// ---- Component -----------------------------------------------------------

const inputClass =
  "px-3 py-1.5 bg-[var(--card-bg)] border border-[var(--border-subtle)] text-[var(--foreground)] text-xs font-bold focus:outline-none focus:border-[var(--accent-cyan)] transition-all";

interface DslFilterBuilderProps {
  group: BuilderGroup;
  onChange: (group: BuilderGroup) => void;
  fields: DslFieldMeta[];
  /** Recursion depth — caps nested-group nesting in the UI. */
  depth?: number;
  /** Internal: hide the "remove group" control on the root group. */
  isRoot?: boolean;
  onRemove?: () => void;
}

const MAX_UI_DEPTH = 3;

export function DslFilterBuilder({
  group,
  onChange,
  fields,
  depth = 0,
  isRoot = true,
  onRemove,
}: DslFilterBuilderProps) {
  const defaultField = fields[0]?.key ?? "RSI";

  const updateChild = (index: number, child: BuilderNode) => {
    const children = group.children.map((c, i) => (i === index ? child : c));
    onChange({ ...group, children });
  };

  const removeChild = (index: number) => {
    onChange({ ...group, children: group.children.filter((_, i) => i !== index) });
  };

  const addClause = () => {
    onChange({ ...group, children: [...group.children, makeClause(defaultField)] });
  };

  const addGroup = () => {
    onChange({ ...group, children: [...group.children, makeGroup("or")] });
  };

  return (
    <div
      className="border border-[var(--border-subtle)] bg-[var(--bg-secondary)]/40 p-3 space-y-2"
      data-testid={isRoot ? "dsl-root-group" : "dsl-subgroup"}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-widest">
            Match
          </span>
          <div className="flex bg-[var(--bg-secondary)] border border-[var(--border-subtle)] p-0.5">
            {(["and", "or"] as const).map((op) => (
              <button
                key={op}
                type="button"
                aria-pressed={group.op === op}
                onClick={() => onChange({ ...group, op })}
                className={`px-4 py-1 text-[10px] font-bold uppercase transition-all ${
                  group.op === op
                    ? "bg-[var(--accent-primary)] text-white"
                    : "text-[var(--text-secondary)] hover:text-[var(--foreground)]"
                }`}
              >
                {op}
              </button>
            ))}
          </div>
        </div>
        {!isRoot && onRemove && (
          <button
            type="button"
            aria-label="Remove group"
            onClick={onRemove}
            className="text-[var(--text-muted)] hover:text-red-500 transition-all p-1.5 bg-[var(--card-hover)] border border-[var(--border-subtle)]"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      <div className="space-y-2">
        {group.children.map((child, i) =>
          child.kind === "group" ? (
            <DslFilterBuilder
              key={i}
              group={child}
              fields={fields}
              depth={depth + 1}
              isRoot={false}
              onChange={(g) => updateChild(i, g)}
              onRemove={() => removeChild(i)}
            />
          ) : (
            <div
              key={i}
              className="flex items-center gap-2 flex-wrap p-2 bg-[var(--bg-secondary)] border border-[var(--border-subtle)]"
              data-testid="dsl-clause-row"
            >
              <select
                aria-label="Field"
                value={child.field}
                onChange={(e) => updateChild(i, { ...child, field: e.target.value })}
                className={`${inputClass} flex-1 min-w-[140px]`}
              >
                {fields.map((f) => (
                  <option key={f.key} value={f.key}>
                    {f.label}
                  </option>
                ))}
              </select>

              <select
                aria-label="Comparator"
                value={child.cmp}
                onChange={(e) =>
                  updateChild(i, { ...child, cmp: e.target.value as DslClause["cmp"] })
                }
                className={`${inputClass} w-16 font-mono`}
              >
                {DSL_BUILDER_COMPARATORS.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>

              <input
                type="number"
                aria-label="Value"
                value={String(child.value)}
                onChange={(e) => updateChild(i, { ...child, value: Number(e.target.value) })}
                className={`w-24 ${inputClass} font-mono`}
                placeholder="VALUE"
              />

              <button
                type="button"
                aria-label="Remove condition"
                onClick={() => removeChild(i)}
                className="text-[var(--text-muted)] hover:text-red-500 transition-all p-1.5 bg-[var(--card-hover)] border border-[var(--border-subtle)]"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ),
        )}
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={addClause}
          className="flex-1 flex items-center justify-center gap-2 py-2 border border-dashed border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--accent-cyan)]/50 hover:text-[var(--foreground)] hover:bg-[var(--card-hover)] transition-all text-[10px] font-bold uppercase tracking-widest"
        >
          + Condition
        </button>
        {depth < MAX_UI_DEPTH && (
          <button
            type="button"
            onClick={addGroup}
            className="flex-1 flex items-center justify-center gap-2 py-2 border border-dashed border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--accent-cyan)]/50 hover:text-[var(--foreground)] hover:bg-[var(--card-hover)] transition-all text-[10px] font-bold uppercase tracking-widest"
          >
            + Group
          </button>
        )}
      </div>
    </div>
  );
}
