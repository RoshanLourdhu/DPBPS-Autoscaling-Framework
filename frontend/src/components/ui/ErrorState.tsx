// src/components/ui/ErrorState.tsx
import React from "react";

interface ErrorStateProps {
  message?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({ message = "Failed to load data" }) => (
  <div className="p-4 text-center text-red-400 border border-red-600 rounded bg-gray-900">
    {message}
  </div>
);
