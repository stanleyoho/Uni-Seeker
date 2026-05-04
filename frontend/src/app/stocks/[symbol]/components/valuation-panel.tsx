"use client";

import React from "react";
import { type ValuationEstimates, type PriceEstimate } from "@/lib/api-client";
import { GlassPanel, KpiCard } from "@/components/stratos/primitives";
import { ScoreBar } from "@/components/ui/score-bar";

interface ValuationPanelProps {
  valuation: ValuationEstimates;
  currentPrice: number;
}

function ValuationCard({ estimate, title }: { estimate: PriceEstimate; title: string }) {
  const fair = parseFloat(estimate.fair_price || "0");
  const cheap = parseFloat(estimate.cheap_price || "0");
  const expensive = parseFloat(estimate.expensive_price || "0");
  const confidence = parseFloat(estimate.confidence) * 100;

  return (
    <div className="bg-[var(--bg-secondary)] rounded-lg p-4 border border-[var(--border-subtle)] space-y-4">
      <div className="flex items-center justify-between">
        <h4 className="text-[10px] uppercase tracking-widest font-bold text-[var(--text-secondary)]">
          {title}
        </h4>
        <div className="flex items-center gap-2">
           <span className="text-[10px] text-[var(--text-muted)] font-bold">CONFIDENCE</span>
           <span className="text-[11px] font-bold text-[var(--accent-cyan)]">{confidence.toFixed(0)}%</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <div className="text-center">
          <span className="text-[9px] text-[var(--text-muted)] uppercase block mb-1">Cheap</span>
          <span className="text-sm font-bold tabular-nums text-[var(--stock-down)]">{cheap > 0 ? cheap.toLocaleString() : "-"}</span>
        </div>
        <div className="text-center border-x border-[var(--border-subtle)]">
          <span className="text-[9px] text-[var(--text-muted)] uppercase block mb-1">Fair</span>
          <span className="text-sm font-bold tabular-nums text-[var(--foreground)]">{fair > 0 ? fair.toLocaleString() : "-"}</span>
        </div>
        <div className="text-center">
          <span className="text-[9px] text-[var(--text-muted)] uppercase block mb-1">Expensive</span>
          <span className="text-sm font-bold tabular-nums text-[var(--stock-up)]">{expensive > 0 ? expensive.toLocaleString() : "-"}</span>
        </div>
      </div>
      
      <ScoreBar label="Confidence" value={confidence} size="sm" />
    </div>
  );
}

export function ValuationPanel({ valuation, currentPrice }: ValuationPanelProps) {
  const comp = valuation.latest_composite;
  if (!comp && valuation.estimates.length === 0) {
    return (
      <GlassPanel>
        <div className="py-20 text-center text-[var(--text-muted)]">
          No valuation models available for this stock yet.
        </div>
      </GlassPanel>
    );
  }

  const fair = comp ? parseFloat(comp.fair_price || "0") : 0;
  const discount = fair > 0 ? ((fair - currentPrice) / fair) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* 1. Composite Valuation Summary */}
      {comp && (
        <GlassPanel title="Composite Valuation">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 items-center">
            <div className="md:col-span-4">
              <KpiCard
                label="Estimated Fair Value"
                value={fair.toLocaleString()}
                delta={`${discount >= 0 ? "+" : ""}${discount.toFixed(1)}%`}
                direction={discount >= 0 ? "up" : "down"}
              />
              <p className="mt-3 text-[10px] text-[var(--text-muted)] uppercase font-bold tracking-wider leading-relaxed">
                Based on a weighted average of {comp.details.models_used?.join(", ")} models.
              </p>
            </div>
            
            <div className="md:col-span-8">
               <div className="relative h-20 w-full bg-[var(--bg-secondary)] rounded-lg overflow-hidden border border-[var(--border-subtle)] flex items-center px-6">
                  {/* Valuation Spectrum */}
                  <div className="absolute inset-0 opacity-10 bg-gradient-to-r from-[var(--stock-down)] via-[var(--foreground)] to-[var(--stock-up)]" />
                  
                  <div className="w-full flex justify-between items-center relative z-10">
                     <div className="flex flex-col items-center">
                        <span className="text-[10px] font-bold text-[var(--stock-down)] uppercase">Cheap</span>
                        <span className="text-lg font-bold tabular-nums">{parseFloat(comp.cheap_price || "0").toLocaleString()}</span>
                     </div>
                     <div className="flex flex-col items-center">
                        <span className="text-[10px] font-bold text-[var(--foreground)] uppercase">Fair</span>
                        <span className="text-lg font-bold tabular-nums">{fair.toLocaleString()}</span>
                     </div>
                     <div className="flex flex-col items-center">
                        <span className="text-[10px] font-bold text-[var(--stock-up)] uppercase">Expensive</span>
                        <span className="text-lg font-bold tabular-nums">{parseFloat(comp.expensive_price || "0").toLocaleString()}</span>
                     </div>
                  </div>

                  {/* Current Price Marker */}
                  {fair > 0 && (
                     <div 
                        className="absolute top-0 bottom-0 w-1 bg-[var(--accent-cyan)] shadow-[0_0_10px_var(--accent-cyan)] z-20"
                        style={{ 
                          left: `${Math.min(95, Math.max(5, (currentPrice / (parseFloat(comp.expensive_price || "1") * 1.2)) * 100))}%` 
                        }}
                     >
                        <div className="absolute -top-1 -left-1.5 w-4 h-4 rounded-full bg-[var(--accent-cyan)] border-2 border-white shadow-md flex items-center justify-center">
                           <div className="w-1 h-1 bg-white rounded-full" />
                        </div>
                        <div className="absolute top-12 left-1/2 -translate-x-1/2 whitespace-nowrap bg-[var(--accent-cyan)] text-white text-[9px] font-bold px-1.5 py-0.5 rounded shadow-sm">
                           CURRENT: {currentPrice.toLocaleString()}
                        </div>
                     </div>
                  )}
               </div>
            </div>
          </div>
        </GlassPanel>
      )}

      {/* 2. Individual Models */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {valuation.estimates.map((est) => (
          <ValuationCard 
            key={est.model_type} 
            estimate={est} 
            title={est.model_type.toUpperCase()} 
          />
        ))}
      </div>
      
      {/* 3. Methodology Disclaimer */}
      <GlassPanel>
        <h4 className="text-[11px] font-bold text-[var(--text-secondary)] uppercase tracking-widest mb-2">Valuation Methodology</h4>
        <p className="text-[11px] text-[var(--text-muted)] leading-relaxed">
          Intrinsic valuation models (DCF, DDM) rely heavily on future growth and discount rate assumptions. 
          Relative valuation (PE Band) assumes the stock will eventually return to its historical multiple mean. 
          Models are for informational purposes only and do not constitute financial advice.
        </p>
      </GlassPanel>
    </div>
  );
}
