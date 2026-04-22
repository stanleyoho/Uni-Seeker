"use client";

import Link from "next/link";
import type { ScreenResult } from "@/lib/api-client";

interface ResultsTableProps {
  results: ScreenResult[];
  total: number;
}

export function ResultsTable({ results, total }: ResultsTableProps) {
  if (results.length === 0) {
    return <p className="text-gray-400 text-sm">No results. Try adjusting your conditions.</p>;
  }

  // Collect all indicator keys from results
  const indicatorKeys = Array.from(
    new Set(results.flatMap((r) => Object.keys(r.indicator_values))),
  );

  return (
    <div>
      <p className="text-sm text-gray-400 mb-2">{total} results found</p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-gray-400 border-b border-gray-700">
            <tr>
              <th className="py-2 px-3">Symbol</th>
              {indicatorKeys.map((key) => (
                <th key={key} className="py-2 px-3">
                  {key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((r) => (
              <tr key={r.symbol} className="border-b border-gray-800 hover:bg-gray-800/50">
                <td className="py-2 px-3">
                  <Link
                    href={`/stocks/${encodeURIComponent(r.symbol)}`}
                    className="text-blue-400 hover:underline"
                  >
                    {r.symbol}
                  </Link>
                </td>
                {indicatorKeys.map((key) => (
                  <td key={key} className="py-2 px-3">
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
