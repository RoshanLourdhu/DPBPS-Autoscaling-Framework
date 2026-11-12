// src/components/ui/FilterDropdown.tsx
import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, Filter, Check } from "lucide-react";

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

export interface FilterDropdownProps {
  label: string;
  options: FilterOption[];
  selected: string;
  onChange: (value: string) => void;
  icon?: React.ComponentType<{ size?: number; className?: string }>;
  className?: string;
}

export const FilterDropdown: React.FC<FilterDropdownProps> = ({
  label,
  options,
  selected,
  onChange,
  icon: Icon = Filter,
  className = "",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find((o) => o.value === selected);

  return (
    <div ref={dropdownRef} className={`relative inline-block ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center space-x-2 px-3 py-1.5 rounded-lg border border-canvas-border bg-canvas-card hover:bg-canvas-hover text-xs font-medium text-text-secondary hover:text-text-primary transition-colors focus:outline-none focus:border-cyan-500"
      >
        <Icon size={13} className="text-cyan-400" />
        <span>{selectedOption ? selectedOption.label : label}</span>
        <ChevronDown size={13} className="text-text-muted opacity-70" />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-1.5 w-48 rounded-xl border border-canvas-border bg-canvas-elevated shadow-card py-1.5 z-50 animate-in fade-in-50 duration-100">
          <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted border-b border-canvas-border/50">
            {label}
          </div>
          {options.map((opt) => {
            const isSelected = opt.value === selected;
            return (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between px-3 py-1.5 text-xs text-left transition-colors ${
                  isSelected
                    ? "bg-cyan-500/10 text-cyan-400 font-medium"
                    : "text-text-secondary hover:bg-canvas-hover hover:text-text-primary"
                }`}
              >
                <div className="flex items-center space-x-2 truncate">
                  {isSelected ? (
                    <Check size={13} className="text-cyan-400 flex-shrink-0" />
                  ) : (
                    <div className="w-3.5 flex-shrink-0" />
                  )}
                  <span className="truncate">{opt.label}</span>
                </div>
                {opt.count !== undefined && (
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-canvas-dark text-text-muted ml-2">
                    {opt.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

