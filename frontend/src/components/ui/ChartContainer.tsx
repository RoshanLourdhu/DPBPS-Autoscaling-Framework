// src/components/ui/ChartContainer.tsx
import React from "react";

interface ChartContainerProps {
  title: string;
  children: React.ReactNode;
  demo?: boolean;
}

export const ChartContainer: React.FC<ChartContainerProps> = ({ title, children, demo = false }) => (
  <div className="bg-charcoal rounded-lg shadow-sm p-4 border border-gray-700 mb-4">
    <h3 className="text-sm text-gray-400 mb-2 flex items-center justify-between">
      <span>{title}</span>
      {demo && <span className="text-xs text-gray-500">(DEMO)</span>}
    </h3>
    <div className="h-64">{children}</div>
  </div>
);
