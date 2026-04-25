interface ScoreBarProps {
  label: string;
  value: number;
  max?: number;
  showValue?: boolean;
  size?: "sm" | "md";
}

function fillColor(value: number): string {
  if (value > 70) return "bg-[var(--score-excellent)]";
  if (value >= 40) return "bg-[var(--score-good)]";
  return "bg-[var(--score-poor)]";
}

function fillGlow(value: number): string {
  if (value > 70) return "shadow-[0_0_6px_rgba(34,197,94,0.3)]";
  if (value >= 40) return "shadow-[0_0_6px_rgba(234,179,8,0.3)]";
  return "shadow-[0_0_6px_rgba(239,68,68,0.3)]";
}

export function ScoreBar({ label, value, max = 100, showValue = true, size = "sm" }: ScoreBarProps) {
  const pct = Math.min((value / max) * 100, 100);
  const height = size === "sm" ? "h-1.5" : "h-2.5";

  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-[var(--text-muted)] w-16 shrink-0 truncate">{label}</span>
      <div className={`flex-1 ${height} bg-[var(--bg-secondary)] rounded-full overflow-hidden`}>
        <div
          className={`h-full rounded-full transition-all duration-700 ease-out ${fillColor(value)} ${fillGlow(value)}`}
          style={{ width: `${pct}%`, animation: "bar-fill 0.8s ease-out" }}
        />
      </div>
      {showValue && (
        <span className="text-[var(--text-secondary)] w-8 text-right mono-nums">{value.toFixed(0)}</span>
      )}
    </div>
  );
}
