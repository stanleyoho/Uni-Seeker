"use client";

interface Tab {
  key: string;
  label: string;
}

interface TabGroupProps {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
  size?: "sm" | "md";
}

export function TabGroup({ tabs, active, onChange, size = "md" }: TabGroupProps) {
  const padding = size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm";

  return (
    <div className="flex gap-1 bg-[var(--bg-secondary)] p-1 rounded-xl overflow-x-auto scrollbar-hide">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={`${padding} flex-shrink-0 font-medium rounded-lg transition-all duration-200 whitespace-nowrap ${
            active === tab.key
              ? "bg-[var(--accent-blue)] text-white shadow-lg shadow-[var(--accent-blue-glow)]"
              : "text-[var(--text-secondary)] hover:text-[var(--foreground)] hover:bg-[var(--card-hover)]"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
