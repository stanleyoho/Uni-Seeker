import { type ReactNode } from "react";

interface EmptyStateProps {
  icon?: ReactNode;
  title?: string;
  message: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, message, action }: EmptyStateProps) {
  return (
    <div className="text-center py-16">
      {icon && <div className="text-[var(--text-muted)] mb-3 flex justify-center">{icon}</div>}
      {title && <h3 className="text-white font-semibold mb-1">{title}</h3>}
      <p className="text-[var(--text-muted)] text-sm">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}

export function ErrorState({ message, onRetry, retryLabel = "Retry" }: ErrorStateProps) {
  return (
    <div className="bg-[var(--stock-up)]/10 border border-[var(--stock-up)]/20 rounded-xl p-6 text-center">
      <p className="text-red-400 mb-3">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-[var(--card-bg)] border border-[var(--border-color)] text-white hover:bg-[var(--card-hover)] transition-all duration-200"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
