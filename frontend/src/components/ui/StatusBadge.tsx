// src/components/ui/StatusBadge.tsx
import React from "react";

export type StatusVariant =
  | "emerald"
  | "amber"
  | "rose"
  | "cyan"
  | "blue"
  | "purple"
  | "slate";

export interface StatusBadgeProps {
  status: string;
  label?: string;
  variant?: StatusVariant;
  pulse?: boolean;
  size?: "xs" | "sm" | "md";
  className?: string;
}

const statusMap: Record<string, { variant: StatusVariant; label?: string }> = {
  HEALTHY: { variant: "emerald" },
  CONNECTED: { variant: "emerald" },
  READY: { variant: "emerald" },
  COMPLETED: { variant: "emerald" },
  HOLD: { variant: "emerald" },
  OK: { variant: "emerald" },

  WARNING: { variant: "amber" },
  DEGRADED: { variant: "amber" },
  SCALE_DOWN: { variant: "amber" },
  DRY_RUN: { variant: "amber" },
  RUNNING: { variant: "cyan" },
  IN_PROGRESS: { variant: "cyan" },

  CRITICAL: { variant: "rose" },
  ERROR: { variant: "rose" },
  DISCONNECTED: { variant: "rose" },
  FAILED: { variant: "rose" },
  SCALE_UP: { variant: "rose" },
  BOTTLENECK: { variant: "rose" },

  NORMAL_OPERATION: { variant: "blue" },
  ROLLING_UPDATE: { variant: "purple" },
  CANARY_DEPLOYMENT: { variant: "amber" },
  SCALE_TEST: { variant: "cyan" },

  NOT_CONNECTED: { variant: "slate" },
  NOT_CONFIGURED: { variant: "slate" },
  UNKNOWN: { variant: "slate" },
};

const variantClasses: Record<
  StatusVariant,
  { bg: string; text: string; border: string; dot: string; dotPulse: string }
> = {
  emerald: {
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    border: "border-emerald-500/30",
    dot: "bg-emerald-400",
    dotPulse: "bg-emerald-400/50",
  },
  amber: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    border: "border-amber-500/30",
    dot: "bg-amber-400",
    dotPulse: "bg-amber-400/50",
  },
  rose: {
    bg: "bg-rose-500/10",
    text: "text-rose-400",
    border: "border-rose-500/30",
    dot: "bg-rose-400",
    dotPulse: "bg-rose-400/50",
  },
  cyan: {
    bg: "bg-cyan-500/10",
    text: "text-cyan-400",
    border: "border-cyan-500/30",
    dot: "bg-cyan-400",
    dotPulse: "bg-cyan-400/50",
  },
  blue: {
    bg: "bg-blue-500/10",
    text: "text-blue-400",
    border: "border-blue-500/30",
    dot: "bg-blue-400",
    dotPulse: "bg-blue-400/50",
  },
  purple: {
    bg: "bg-purple-500/10",
    text: "text-purple-400",
    border: "border-purple-500/30",
    dot: "bg-purple-400",
    dotPulse: "bg-purple-400/50",
  },
  slate: {
    bg: "bg-slate-800",
    text: "text-slate-300",
    border: "border-slate-700",
    dot: "bg-slate-400",
    dotPulse: "bg-slate-400/50",
  },
};

const sizeClasses = {
  xs: "px-1.5 py-0.5 text-[10px]",
  sm: "px-2.5 py-1 text-xs",
  md: "px-3 py-1.5 text-sm",
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  label,
  variant,
  pulse = false,
  size = "sm",
  className = "",
}) => {
  const normalized = status.toUpperCase();
  const mapped = statusMap[normalized];
  const finalVariant = variant || mapped?.variant || "slate";
  const displayText = label || mapped?.label || status;
  const styles = variantClasses[finalVariant];

  return (
    <span
      className={`inline-flex items-center space-x-1.5 rounded-full font-medium font-mono border ${
        styles.bg
      } ${styles.text} ${styles.border} ${sizeClasses[size]} ${className}`}
    >
      <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
        {pulse && (
          <span
            className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${styles.dotPulse}`}
          />
        )}
        <span
          className={`relative inline-flex rounded-full h-1.5 w-1.5 ${styles.dot}`}
        />
      </span>
      <span className="truncate">{displayText}</span>
    </span>
  );
};
