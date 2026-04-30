"use client";

function formatMoney(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

interface EquityChartProps {
  data: number[];
  label: string;
  height?: number;
  comparison?: number[];
  comparisonLabel?: string;
}

export function EquityChart({
  data,
  label,
  height = 300,
  comparison,
  comparisonLabel,
}: EquityChartProps) {
  if (data.length < 2) return null;

  const W = 800;
  const H = height;
  const PAD = 40;

  // Compute bounds across both datasets
  let allValues = [...data];
  if (comparison && comparison.length >= 2) {
    allValues = [...allValues, ...comparison];
  }
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => {
        const x = PAD + (i / (values.length - 1)) * (W - PAD * 2);
        const y = H - PAD - ((v - min) / range) * (H - PAD * 2);
        return `${x},${y}`;
      })
      .join(" ");

  const points = toPoints(data);

  // Build gradient fill path
  const firstX = PAD;
  const lastX = PAD + ((data.length - 1) / (data.length - 1)) * (W - PAD * 2);
  const fillPath = `M${firstX},${H - PAD} L${points.split(" ").join(" L")} L${lastX},${H - PAD} Z`;

  // Grid lines (4 horizontal)
  const gridLines = Array.from({ length: 5 }, (_, i) => {
    const y = PAD + (i / 4) * (H - PAD * 2);
    const val = max - (i / 4) * range;
    return { y, label: formatMoney(val) };
  });

  const comparisonPoints = comparison && comparison.length >= 2 ? toPoints(comparison) : null;

  return (
    <div className="w-full overflow-x-auto">
      <div className="flex items-center gap-4 mb-2">
        <h3 className="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider">
          {label}
        </h3>
        {comparisonLabel && (
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <span className="inline-block w-3 h-0.5 bg-[#3b82f6] rounded" />
            <span>{label}</span>
            <span className="inline-block w-3 h-0.5 bg-[#f59e0b] rounded" />
            <span>{comparisonLabel}</span>
          </div>
        )}
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full max-w-3xl"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`${label} chart`}
      >
        <defs>
          <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
          </linearGradient>
        </defs>
        {/* Grid */}
        {gridLines.map((g, i) => (
          <g key={i}>
            <line
              x1={PAD}
              y1={g.y}
              x2={W - PAD}
              y2={g.y}
              stroke="rgba(255,255,255,0.04)"
              strokeWidth="1"
            />
            <text
              x={PAD - 4}
              y={g.y + 4}
              textAnchor="end"
              fill="#475569"
              fontSize="10"
              fontFamily="monospace"
            >
              {g.label}
            </text>
          </g>
        ))}
        {/* Gradient fill */}
        <path d={fillPath} fill="url(#equityGradient)" />
        {/* Main line */}
        <polyline
          fill="none"
          stroke="#3b82f6"
          strokeWidth="2"
          points={points}
          style={{ filter: "drop-shadow(0 0 4px rgba(59, 130, 246, 0.4))" }}
        />
        {/* Comparison line */}
        {comparisonPoints && (
          <polyline
            fill="none"
            stroke="#f59e0b"
            strokeWidth="1.5"
            points={comparisonPoints}
            strokeDasharray="6 3"
            style={{ filter: "drop-shadow(0 0 3px rgba(245, 158, 11, 0.3))" }}
          />
        )}
      </svg>
    </div>
  );
}
