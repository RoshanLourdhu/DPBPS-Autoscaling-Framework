// src/components/ui/EmptyState.tsx
import React from "react";
import { Inbox } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface EmptyStateProps {
  title?: string;
  message: string;
  icon?: LucideIcon;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = "No Data Available",
  message,
  icon: Icon = Inbox,
  action,
  className = "",
}) => {
  return (
    <div
      className={`flex flex-col items-center justify-center p-12 text-center rounded-xl bg-canvas-card border border-canvas-border shadow-card min-h-[220px] ${className}`}
    >
      <div className="p-3.5 rounded-full bg-slate-800/80 text-text-muted mb-3.5 border border-canvas-border">
        <Icon size={24} className="opacity-80 text-slate-300" />
      </div>
      <h3 className="text-sm font-semibold text-text-primary mb-1">{title}</h3>
      <p className="text-xs text-text-secondary max-w-sm leading-relaxed mb-4">
        {message}
      </p>
      {action && (
        <button
          onClick={action.onClick}
          className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
};
