// src/components/ui/LoadingState.tsx
import React from "react";
import { Loader2 } from "lucide-react";

export interface LoadingStateProps {
  message?: string;
  variant?: "spinner" | "skeleton" | "compact";
  className?: string;
}

export const LoadingState: React.FC<LoadingStateProps> = ({
  message = "Loading telemetry data...",
  variant = "spinner",
  className = "",
}) => {
  if (variant === "compact") {
    return (
      <div className={`flex items-center space-x-2 text-xs text-text-muted py-2 ${className}`}>
        <Loader2 size={14} className="animate-spin text-cyan-400" />
        <span>{message}</span>
      </div>
    );
  }

  if (variant === "skeleton") {
    return (
      <div className={`space-y-3 p-4 animate-pulse ${className}`}>
        <div className="h-6 bg-slate-800 rounded w-1/3"></div>
        <div className="h-24 bg-slate-800/60 rounded-xl"></div>
        <div className="grid grid-cols-3 gap-3">
          <div className="h-16 bg-slate-800/40 rounded-lg"></div>
          <div className="h-16 bg-slate-800/40 rounded-lg"></div>
          <div className="h-16 bg-slate-800/40 rounded-lg"></div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex flex-col items-center justify-center p-12 text-center rounded-xl bg-canvas-card/40 border border-canvas-border/50 min-h-[220px] ${className}`}
    >
      <div className="relative mb-3">
        <div className="w-10 h-10 rounded-full border-2 border-cyan-500/20 border-t-cyan-400 animate-spin" />
      </div>
      <p className="text-xs font-medium text-text-secondary">{message}</p>
      <p className="text-[11px] text-text-muted mt-1 font-mono">
        Querying Kubernetes telemetry and Prometheus series
      </p>
    </div>
  );
};
