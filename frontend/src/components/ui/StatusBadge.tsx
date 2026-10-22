// src/components/ui/StatusBadge.tsx
import React from "react";

interface StatusBadgeProps {
  status: string;
}

const statusColors: Record<string, string> = {
  CONNECTED: "bg-green-600",
  DISCONNECTED: "bg-red-600",
  NOT_CONNECTED: "bg-gray-600",
  NOT_CONFIGURED: "bg-yellow-600",
  ERROR: "bg-red-800",
  UNKNOWN: "bg-gray-500",
};

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const upper = status.toUpperCase();
  const colorClass = statusColors[upper] || statusColors["UNKNOWN"];
  return (
    <span className={`inline-block px-2 py-1 text-xs font-medium rounded ${colorClass} text-white`}>
      {upper}
    </span>
  );
};
