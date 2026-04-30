"use client";

import { type ReactNode, useState } from "react";

export interface Column<T> {
  key: string;
  header: string;
  align?: "left" | "center" | "right";
  width?: string;
  sortable?: boolean;
  render: (row: T, index: number) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  compact?: boolean;
  isLoading?: boolean;
}

export function DataTable<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  emptyMessage = "No data",
  compact = false,
  isLoading = false,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const cellPadding = compact ? "px-3 py-2" : "px-4 py-3";

  if (!isLoading && data.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-[var(--text-muted)]">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border-color)] text-[var(--text-muted)] text-xs uppercase tracking-wider">
            {columns.map((col) => (
              <th
                key={col.key}
                role="columnheader"
                aria-sort={col.sortable ? (sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : "none") : undefined}
                tabIndex={col.sortable ? 0 : undefined}
                className={`${cellPadding} text-${col.align || "left"} ${col.width || ""} ${
                  col.sortable ? "cursor-pointer select-none hover:text-white transition-colors" : ""
                }`}
                onClick={col.sortable ? () => handleSort(col.key) : undefined}
                onKeyDown={col.sortable ? (e: React.KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleSort(col.key); } } : undefined}
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {col.sortable && sortKey === col.key && (
                    <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 12 12">
                      {sortDir === "asc" ? (
                        <path d="M6 3l4 5H2z" />
                      ) : (
                        <path d="M6 9l4-5H2z" />
                      )}
                    </svg>
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading && Array.from({ length: 5 }).map((_, i) => (
            <tr key={`skeleton-${i}`} className="border-t border-[var(--border-subtle)]">
              {columns.map((_, j) => (
                <td key={j} className="py-2 px-3">
                  <div className="h-3 bg-[var(--bg-secondary)] rounded animate-pulse w-3/4" />
                </td>
              ))}
            </tr>
          ))}
          {!isLoading && data.map((row, idx) => (
            <tr
              key={rowKey(row)}
              role="row"
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-[var(--border-subtle)] hover:bg-[var(--card-active)]/40 transition-colors duration-150 ${
                idx % 2 === 1 ? "bg-[var(--background)]/30" : ""
              } ${onRowClick ? "cursor-pointer" : ""}`}
            >
              {columns.map((col) => (
                <td key={col.key} className={`${cellPadding} ${col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left"}`}>
                  {col.render(row, idx)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
