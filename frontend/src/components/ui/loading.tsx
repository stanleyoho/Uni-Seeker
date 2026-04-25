interface LoadingSpinnerProps {
  text?: string;
  size?: "sm" | "md" | "lg";
  fullPage?: boolean;
}

const sizeMap = {
  sm: { box: "w-5 h-5", ring: 18, stroke: 2 },
  md: { box: "w-8 h-8", ring: 30, stroke: 2.5 },
  lg: { box: "w-12 h-12", ring: 46, stroke: 3 },
};

export function LoadingSpinner({ text, size = "md", fullPage = false }: LoadingSpinnerProps) {
  const s = sizeMap[size];
  const r = s.ring / 2 - s.stroke;
  const circumference = 2 * Math.PI * r;

  const content = (
    <div className="flex flex-col items-center gap-3">
      <div className={`${s.box} relative animate-pulse-glow`} style={{ animation: "ring-pulse 1.5s ease-in-out infinite" }}>
        <svg className={`${s.box} animate-spin`} viewBox={`0 0 ${s.ring} ${s.ring}`} fill="none">
          {/* Track ring */}
          <circle
            cx={s.ring / 2}
            cy={s.ring / 2}
            r={r}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={s.stroke}
          />
          {/* Active arc */}
          <circle
            cx={s.ring / 2}
            cy={s.ring / 2}
            r={r}
            stroke="var(--accent-blue)"
            strokeWidth={s.stroke}
            strokeLinecap="round"
            strokeDasharray={`${circumference * 0.3} ${circumference * 0.7}`}
            style={{
              filter: "drop-shadow(0 0 4px rgba(59, 130, 246, 0.5))",
            }}
          />
        </svg>
      </div>
      {text && <span className="text-[var(--text-muted)] text-sm">{text}</span>}
    </div>
  );

  if (fullPage) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        {content}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center py-12">
      {content}
    </div>
  );
}
