// src/components/ui/MetricCard.tsx
import React from "react";
import { ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";

export interface MetricTrend {
  value: number | string;
  isPositive?: boolean;
  label?: string;
}

export interface MetricCardProps {
  title: string;
  value: number | string;
  unit?: string;
  subtext?: string;
  trend?: MetricTrend;
  icon?: LucideIcon;
  variant?: "cyan" | "blue" | "emerald" | "amber" | "rose" | "purple" | "slate";
  to?: string;
  onClick?: () => void;
  loading?: boolean;
  demo?: boolean;
  className?: string;
}

const variantStyles: Record<
  NonNullable<MetricCardProps["variant"]>,
  { border: string; glow: string; text: string; iconBg: string }
> = {
  cyan: {
    border: "border-t-2 border-t-cyan-500",
    glow: "hover:shadow-[0_4px_20px_rgba(6,182,212,0.15)]",
    text: "text-cyan-400",
    iconBg: "bg-cyan-500/10 text-cyan-400",
  },
  blue: {
    border: "border-t-2 border-t-blue-500",
    glow: "hover:shadow-[0_4px_20px_rgba(59,130,246,0.15)]",
    text: "text-blue-400",
    iconBg: "bg-blue-500/10 text-blue-400",
  },
  emerald: {
    border: "border-t-2 border-t-emerald-500",
    glow: "hover:shadow-[0_4px_20px_rgba(16,185,129,0.15)]",
    text: "text-emerald-400",
    iconBg: "bg-emerald-500/10 text-emerald-400",
  },
  amber: {
    border: "border-t-2 border-t-amber-500",
    glow: "hover:shadow-[0_4px_20px_rgba(245,158,11,0.15)]",
    text: "text-amber-400",
    iconBg: "bg-amber-500/10 text-amber-400",
  },
  rose: {
    border: "border-t-2 border-t-rose-500",
    glow: "hover:shadow-[0_4px_20px_rgba(239,68,68,0.15)]",
    text: "text-rose-400",
    iconBg: "bg-rose-500/10 text-rose-400",
  },
  purple: {
    border: "border-t-2 border-t-purple-500",
    glow: "hover:shadow-[0_4px_20px_rgba(139,92,246,0.15)]",
    text: "text-purple-400",
    iconBg: "bg-purple-500/10 text-purple-400",
  },
  slate: {
    border: "border-t-2 border-t-slate-600",
    glow: "hover:shadow-card",
    text: "text-slate-200",
    iconBg: "bg-slate-800 text-slate-300",
  },
};

export const MetricCard: React.FC<MetricCardProps> = ({
  title,
  value,
  unit = "",
  subtext,
  trend,
  icon: Icon,
  variant = "cyan",
  to,
  onClick,
  loading = false,
  demo = false,
  className = "",
}) => {
  const styles = variantStyles[variant];

  const content = (
    <div
      onClick={onClick}
      className={`relative bg-canvas-card border border-canvas-border rounded-xl p-5 shadow-card transition-all duration-200 ${
        styles.border
      } ${styles.glow} ${
        to || onClick ? "cursor-pointer hover:border-slate-600 hover:-translate-y-0.5" : ""
      } ${className}`}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium uppercase tracking-wider text-text-secondary truncate pr-2">
          {title}
        </span>
        {Icon && (
          <div className={`p-2 rounded-lg ${styles.iconBg} flex-shrink-0`}>
            <Icon size={16} />
          </div>
        )}
      </div>

      {loading ? (
        <div className="space-y-2 py-1 animate-pulse">
          <div className="h-8 bg-slate-800 rounded w-2/3"></div>
          <div className="h-3 bg-slate-800 rounded w-1/2"></div>
        </div>
      ) : (
        <>
          <div className="flex items-baseline space-x-1.5">
            <span className="text-2xl font-bold font-mono text-text-primary tracking-tight">
              {value}
            </span>
            {unit && (
              <span className="text-xs font-mono text-text-muted">{unit}</span>
            )}
            {demo && (
              <span className="ml-2 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                SIM
              </span>
            )}
          </div>

          {(trend || subtext) && (
            <div className="mt-3 pt-2.5 border-t border-canvas-border flex items-center justify-between text-xs">
              {trend ? (
                <div
                  className={`flex items-center space-x-1 font-mono ${
                    trend.isPositive === true
                      ? "text-emerald-400"
                      : trend.isPositive === false
                      ? "text-rose-400"
                      : "text-text-muted"
                  }`}
                >
                  {trend.isPositive === true ? (
                    <ArrowUpRight size={13} />
                  ) : trend.isPositive === false ? (
                    <ArrowDownRight size={13} />
                  ) : (
                    <Minus size={13} />
                  )}
                  <span>{trend.value}</span>
                  {trend.label && (
                    <span className="text-[11px] text-text-muted font-sans">
                      {trend.label}
                    </span>
                  )}
                </div>
              ) : (
                <div />
              )}

              {subtext && (
                <span className="text-[11px] text-text-muted truncate ml-2">
                  {subtext}
                </span>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} className="block no-underline">
        {content}
      </Link>
    );
  }

  return content;
};
