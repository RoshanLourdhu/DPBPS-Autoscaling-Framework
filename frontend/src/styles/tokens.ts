// src/styles/tokens.ts
/**
 * Centralized Design System Tokens for DPBPS Observability Platform
 */

export const colors = {
  canvas: {
    dark: "#0b0f19",
    base: "#0f172a",
    card: "#111827",
    elevated: "#1e293b",
    border: "#1f293d",
    hover: "#283548",
    subtle: "#161f30",
  },
  text: {
    primary: "#f9fafb",
    secondary: "#9ca3af",
    muted: "#6b7280",
    white: "#ffffff",
  },
  accent: {
    cyan: "#06b6d4",
    blue: "#3b82f6",
    indigo: "#6366f1",
    purple: "#8b5cf6",
  },
  status: {
    emerald: "#10b981",
    amber: "#f59e0b",
    rose: "#ef4444",
    slate: "#64748b",
  },
} as const;

export const shadows = {
  card: "0 4px 20px -2px rgba(0, 0, 0, 0.4)",
  cardHover: "0 8px 30px -4px rgba(6, 182, 212, 0.12)",
  glowCyan: "0 0 15px rgba(6, 182, 212, 0.25)",
  glowPurple: "0 0 15px rgba(139, 92, 246, 0.25)",
  glowRose: "0 0 15px rgba(239, 68, 68, 0.25)",
} as const;

export const transitions = {
  fast: "150ms cubic-bezier(0.4, 0, 0.2, 1)",
  default: "200ms cubic-bezier(0.4, 0, 0.2, 1)",
  smooth: "300ms cubic-bezier(0.4, 0, 0.2, 1)",
} as const;

