"use client";

import { useState } from "react";
import { ConditionBuilder } from "@/components/screener/condition-builder";
import { ResultsTable } from "@/components/screener/results-table";
import {
  screenStocks,
  type ScreenCondition,
  type ScreenResult,
} from "@/lib/api-client";

export default function ScreenerPage() {
  const [conditions, setConditions] = useState<ScreenCondition[]>([]);
  const [logicOp, setLogicOp] = useState<"AND" | "OR">("AND");
  const [results, setResults] = useState<ScreenResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [limit, setLimit] = useState(50);

  const handleScreen = async () => {
    if (conditions.length === 0) {
      setError("Add at least one condition.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await screenStocks(conditions, logicOp, undefined, limit);
      setResults(res.results);
      setTotal(res.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Screen request failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Stock Screener</h1>

      <div className="bg-gray-800 rounded-lg p-4 mb-6">
        <h2 className="text-lg font-semibold mb-3">Conditions</h2>
        <ConditionBuilder
          conditions={conditions}
          onChange={setConditions}
          logicOperator={logicOp}
          onLogicChange={setLogicOp}
        />

        <div className="flex items-center gap-4 mt-4">
          <label className="text-sm text-gray-400">
            Limit:
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value) || 50)}
              className="ml-2 w-20 px-2 py-1 rounded bg-gray-700 border border-gray-600 text-white text-sm"
            />
          </label>
          <button
            onClick={handleScreen}
            disabled={loading}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50"
          >
            {loading ? "Screening..." : "Screen"}
          </button>
        </div>

        {error && <p className="text-red-500 text-sm mt-2">{error}</p>}
      </div>

      <div className="bg-gray-800 rounded-lg p-4">
        <h2 className="text-lg font-semibold mb-3">Results</h2>
        <ResultsTable results={results} total={total} />
      </div>
    </div>
  );
}
