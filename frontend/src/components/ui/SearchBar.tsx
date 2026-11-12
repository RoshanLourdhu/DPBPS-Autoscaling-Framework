// src/components/ui/SearchBar.tsx
import React from "react";
import { Search, X } from "lucide-react";

export interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  onClear?: () => void;
  className?: string;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  placeholder = "Search...",
  onClear,
  className = "",
}) => {
  return (
    <div className={`relative flex items-center ${className}`}>
      <Search
        size={14}
        className="absolute left-3 text-text-muted pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-canvas-dark border border-canvas-border rounded-lg pl-9 pr-8 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 transition-colors"
      />
      {value && (
        <button
          onClick={() => {
            onChange("");
            onClear?.();
          }}
          className="absolute right-2.5 text-text-muted hover:text-text-primary transition-colors"
        >
          <X size={13} />
        </button>
      )}
    </div>
  );
};

