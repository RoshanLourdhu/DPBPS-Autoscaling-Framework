// src/components/ui/ConfirmationDialog.tsx
import React, { useEffect } from "react";
import { AlertTriangle, AlertCircle, HelpCircle, X } from "lucide-react";

export interface ConfirmationDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "warning" | "primary";
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmationDialog: React.FC<ConfirmationDialogProps> = ({
  isOpen,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "primary",
  onConfirm,
  onCancel,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  const variantStyles = {
    danger: {
      icon: AlertCircle,
      iconBg: "bg-rose-500/20 text-rose-400",
      btnConfirm: "bg-rose-600 hover:bg-rose-700 text-white focus:ring-rose-500",
    },
    warning: {
      icon: AlertTriangle,
      iconBg: "bg-amber-500/20 text-amber-400",
      btnConfirm: "bg-amber-600 hover:bg-amber-700 text-white focus:ring-amber-500",
    },
    primary: {
      icon: HelpCircle,
      iconBg: "bg-cyan-500/20 text-cyan-400",
      btnConfirm: "bg-cyan-600 hover:bg-cyan-700 text-white focus:ring-cyan-500",
    },
  }[variant];

  const Icon = variantStyles.icon;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="relative w-full max-w-md bg-canvas-card border border-canvas-border rounded-xl p-6 shadow-2xl space-y-4">
        <button
          onClick={onCancel}
          className="absolute top-4 right-4 text-text-muted hover:text-text-primary transition-colors"
        >
          <X size={16} />
        </button>

        <div className="flex items-start space-x-3.5">
          <div className={`p-2.5 rounded-xl ${variantStyles.iconBg} flex-shrink-0`}>
            <Icon size={20} />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-semibold text-text-primary">{title}</h3>
            <p className="text-xs text-text-secondary leading-relaxed">{message}</p>
          </div>
        </div>

        <div className="flex items-center justify-end space-x-2.5 pt-3 border-t border-canvas-border">
          <button
            type="button"
            onClick={onCancel}
            className="px-3.5 py-1.5 rounded-lg border border-canvas-border bg-canvas-elevated hover:bg-canvas-hover text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
          >
            {cancelText}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-canvas-dark ${variantStyles.btnConfirm}`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
};

