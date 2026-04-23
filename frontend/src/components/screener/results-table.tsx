"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ScreenResult } from "@/lib/api-client";

interface ResultsTableProps {
  results: ScreenResult[];
  total: number;
}

export function ResultsTable({ results, total }: ResultsTableProps) {
  const router = useRouter();

  if (results.length === 0) {
    return (
      <div className="text-center py-12">
        <svg className="w-12 h-12 mx-auto text-[#1e293b] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <p className="text-[#64748b] text-sm">No results. Try adjusting your conditions.</p>
      </div>
    );
  }

  // Collect all indicator keys from results
  const indicatorKeys = Array.from(
    new Set(results.flatMap((r) => Object.keys(r.indicator_values))),
  );

  return (
    <div>
      <p className="text-sm text-[#64748b] mb-3">{total} results found</p>
      <div className="overflow-x-auto rounded-xl border border-[#1e293b]">
        <table className="w-full text-sm text-left">
          <thead className="text-[#64748b] text-xs uppercase tracking-wider bg-[#111827]">
            <tr>
              <th className="py-3 px-4 font-medium">Symbol</th>
              {indicatorKeys.map((key) => (
                <th key={key} className="py-3 px-4 font-medium">
                  {key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((r, i) => (
              <tr
                key={r.symbol}
                onClick={() => router.push(`/stocks/${encodeURIComponent(r.symbol)}`)}
                className={`border-t border-[#1e293b] cursor-pointer transition-all duration-150 hover:bg-[#1e293b] ${
                  i % 2 === 0 ? "bg-[#1a2332]" : "bg-[#111827]/50"
                }`}
              >
                <td className="py-3 px-4">
                  <Link
                    href={`/stocks/${encodeURIComponent(r.symbol)}`}
                    className="text-blue-400 hover:text-blue-300 font-mono font-semibold transition-colors duration-200"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {r.symbol}
                  </Link>
                </td>
                {indicatorKeys.map((key) => (
                  <td key={key} className="py-3 px-4 font-mono text-[#94a3b8]">
                    {r.indicator_values[key] != null
                      ? Number(r.indicator_values[key]).toFixed(2)
                      : "-"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
