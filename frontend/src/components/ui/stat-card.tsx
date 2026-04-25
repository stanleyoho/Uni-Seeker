interface StatCardProps {
  label: string;
  value: string | number;
  change?: number | null;
  changeLabel?: string;
  className?: string;
  size?: "sm" | "md" | "lg";
}

export function StatCard({ label, value, change, changeLabel, className = "", size = "md" }: StatCardProps) {
  const isUp = change != null && change >= 0;
  const sizeClasses = {
    sm: "p-3",
    md: "p-4",
    lg: "p-5",
  };

  return (
    <div
      className={`bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl ${sizeClasses[size]} transition-all duration-200 hover:bg-[var(--card-hover)] ${className}`}
    >
      <span className="text-[var(--text-muted)] text-xs uppercase tracking-wider font-medium">
        {label}
      </span>
      <div className="flex items-baseline gap-2 mt-1">
        <p className={`font-semibold text-white mono-nums ${size === "lg" ? "text-2xl" : "text-xl"}`}>
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
        {change != null && (
          <span
            className={`text-xs font-semibold px-1.5 py-0.5 rounded mono-nums ${
              isUp
                ? "text-[var(--stock-up)] bg-[var(--stock-up-bg)]"
                : "text-[var(--stock-down)] bg-[var(--stock-down-bg)]"
            }`}
          >
            {isUp ? "+" : ""}
            {typeof change === "number" ? change.toFixed(2) : change}
            {changeLabel ? ` ${changeLabel}` : "%"}
          </span>
        )}
      </div>
    </div>
  );
}
