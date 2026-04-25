import { type ReactNode } from "react";

type BadgeVariant = "default" | "up" | "down" | "flat" | "blue" | "score-excellent" | "score-good" | "score-poor";

const variantClasses: Record<BadgeVariant, string> = {
  default: "text-[var(--text-secondary)] bg-[var(--card-hover)] border-[var(--border-color)]",
  up: "text-[var(--stock-up)] bg-[var(--stock-up-bg)] border-[var(--stock-up)]/20 glow-red",
  down: "text-[var(--stock-down)] bg-[var(--stock-down-bg)] border-[var(--stock-down)]/20 glow-green",
  flat: "text-[var(--stock-flat)] bg-[var(--bg-secondary)] border-[var(--border-color)]",
  blue: "text-[var(--accent-blue)] bg-[var(--accent-blue)]/10 border-[var(--accent-blue)]/20 glow-blue",
  "score-excellent": "text-[var(--score-excellent)] bg-[var(--score-excellent)]/10 border-[var(--score-excellent)]/20 glow-green",
  "score-good": "text-[var(--score-good)] bg-[var(--score-good)]/10 border-[var(--score-good)]/20 glow-amber",
  "score-poor": "text-[var(--score-poor)] bg-[var(--score-poor)]/10 border-[var(--score-poor)]/20 glow-red",
};

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ children, variant = "default", className = "" }: BadgeProps) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-md border ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  );
}

export function ScoreBadge({ score, className = "" }: { score: number; className?: string }) {
  const variant: BadgeVariant = score > 70 ? "score-excellent" : score >= 40 ? "score-good" : "score-poor";
  return (
    <Badge variant={variant} className={`text-sm font-bold px-2.5 py-1 rounded-lg mono-nums ${className}`}>
      {score.toFixed(1)}
    </Badge>
  );
}

export function MarketBadge({ market }: { market: string }) {
  if (market.startsWith("TW_TWSE")) return <Badge variant="default">TWSE</Badge>;
  if (market.startsWith("TW_TPEX")) return <Badge variant="default">TPEX</Badge>;
  if (market.includes("NASDAQ")) return <Badge variant="blue">NASDAQ</Badge>;
  if (market.includes("NYSE")) return <Badge variant="blue">NYSE</Badge>;
  return <Badge>{market}</Badge>;
}

export function ChangeBadge({ change, changePct }: { change: number; changePct?: string }) {
  const isUp = change >= 0;
  return (
    <Badge variant={change === 0 ? "flat" : isUp ? "up" : "down"} className="text-sm font-semibold px-2.5 py-1 rounded-lg mono-nums">
      {isUp ? "+" : ""}
      {change.toFixed(2)}
      {changePct != null && ` (${changePct}%)`}
    </Badge>
  );
}
