// src/components/ui/LoadingState.tsx
import React from "react";

export const LoadingState: React.FC = () => (
  <div className="flex items-center justify-center py-8 text-gray-400">
    <svg className="animate-spin h-6 w-6 mr-2 text-accent-cyan" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg>
    Loading...
  </div>
);
