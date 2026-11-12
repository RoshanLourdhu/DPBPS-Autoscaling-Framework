// src/components/ui/SectionHeader.tsx
import React from "react";
import type { LucideIcon } from "lucide-react";

export interface SectionHeaderProps {
  title: string;
  subtitle?: string;
  icon?: LucideIcon;
  badge?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  subtitle,
  icon: Icon,
  badge,
  action,
  className = "",
}) => {
  return (
    <div
      className={`flex items-center justify-between py-2 mb-3 border-b border-canvas-border ${className}`}
    >
      <div className="flex items-center space-x-2.5">
        {Icon && (
          <div className="p-1.5 rounded-md bg-canvas-elevated text-cyan-400">
            <Icon size={16} />
          </div>
        )}
        <div>
          <div className="flex items-center space-x-2">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-text-primary">
              {title}
            </h2>
            {badge}
          </div>
          {subtitle && (
            <p className="text-[11px] text-text-muted mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>

      {action && <div className="flex items-center space-x-2">{action}</div>}
    </div>
  );
};
