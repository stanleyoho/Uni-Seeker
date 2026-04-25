import { type ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingMap = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-5",
};

export function Card({ children, className = "", hover = false, padding = "md" }: CardProps) {
  return (
    <div
      className={`bg-[var(--card-bg)] border border-[var(--border-color)] rounded-xl ${paddingMap[padding]} ${
        hover ? "hover:bg-[var(--card-hover)] hover:border-[rgba(255,255,255,0.1)] transition-all duration-200" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function GlassCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`glass border border-[var(--border-color)] rounded-2xl p-5 shadow-xl shadow-black/30 ${className}`}>
      {children}
    </div>
  );
}
