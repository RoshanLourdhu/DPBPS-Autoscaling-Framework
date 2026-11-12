// src/components/ui/PageHeader.tsx
import React from "react";

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  badge?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  badge,
  actions,
  className = "",
}) => {
  return (
    <div
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-canvas-border ${className}`}
    >
      <div className="space-y-1">
        <div className="flex items-center space-x-3">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
            {title}
          </h1>
          {badge}
        </div>
        {subtitle && (
          <p className="text-xs sm:text-sm text-text-secondary leading-relaxed max-w-3xl">
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center space-x-2.5 flex-shrink-0">
          {actions}
        </div>
      )}
    </div>
  );
};
