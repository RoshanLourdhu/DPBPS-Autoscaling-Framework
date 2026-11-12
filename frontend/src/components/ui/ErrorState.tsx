// src/components/ui/ErrorState.tsx
import React, { useState } from "react";
import { AlertCircle, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";

export interface ErrorStateProps {
  message: string;
  title?: string;
  onRetry?: () => void;
  details?: string;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  message,
  title = "Telemetry Error",
  onRetry,
  details,
  className = "",
}) => {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div
      className={`rounded-xl bg-rose-500/10 border border-rose-500/30 p-5 shadow-card text-left ${className}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start space-x-3">
          <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 flex-shrink-0 mt-0.5">
            <AlertCircle size={18} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-rose-400">{title}</h3>
            <p className="text-xs text-rose-200/90 mt-1 leading-relaxed">{message}</p>
          </div>
        </div>

        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 border border-rose-500/30 transition-colors flex-shrink-0"
          >
            <RefreshCw size={13} />
            <span>Retry</span>
          </button>
        )}
      </div>

      {details && (
        <div className="mt-4 pt-3 border-t border-rose-500/20">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center space-x-1 text-[11px] font-mono text-rose-300/80 hover:text-rose-200"
          >
            <span>{showDetails ? "Hide technical stack" : "Show technical stack"}</span>
            {showDetails ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          {showDetails && (
            <pre className="mt-2 p-2.5 rounded bg-black/40 border border-rose-500/20 text-[10px] font-mono text-rose-200 overflow-x-auto whitespace-pre-wrap">
              {details}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};
