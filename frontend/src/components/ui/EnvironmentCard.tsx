// src/components/ui/EnvironmentCard.tsx
import React from "react";
import { StatusBadge } from "./StatusBadge";

interface EnvironmentCardProps {
  name: string;
  description?: string;
  status: string;
  demo?: boolean;
}

export const EnvironmentCard: React.FC<EnvironmentCardProps> = ({ name, description, status, demo = false }) => (
  <div className="bg-charcoal rounded-lg shadow-sm p-4 border border-gray-700 mb-4">
    <div className="flex items-center justify-between">
      <h3 className="text-lg font-medium text-gray-200">{name}</h3>
      <StatusBadge status={status} />
    </div>
    {description && <p className="text-sm text-gray-400 mt-2">{description}</p>}
    {demo && <span className="text-xs text-gray-500 mt-2 block">(DEMO)</span>}
  </div>
);
