// src/components/ui/EmptyState.tsx
import React from "react";

interface EmptyStateProps {
  message?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({ message = "No data available" }) => (
  <div className="p-6 text-center text-gray-500 border border-gray-700 rounded bg-gray-800">
    {message}
  </div>
);
