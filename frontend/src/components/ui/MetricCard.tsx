// src/components/ui/MetricCard.tsx
import React from "react";

interface MetricCardProps {
  title: string;
  value: number | string;
  unit?: string;
  demo?: boolean;
}

export const MetricCard: React.FC<MetricCardProps> = ({ title, value, unit = "", demo = false }) => {
  return (
    <div className="bg-charcoal rounded-lg shadow-sm p-4 border border-gray-700">
      <h3 className="text-sm text-gray-400 mb-2">{title}</h3>
      <p className="text-2xl font-medium text-accent-cyan">
        {value} {unit}
        {demo && <span className="ml-2 text-xs text-gray-500">(DEMO)</span>}
      </p>
    </div>
  );
};
