// tailwind.config.cjs
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}"
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Deep canvas background and surfaces
        canvas: {
          dark: "#0b0f19",      // Deepest page background
          base: "#0f172a",      // Alternate dark slate/navy
          card: "#111827",      // Primary card & container surface
          elevated: "#1e293b",  // Elevated surfaces, headers, dropdowns
          border: "#1f293d",    // Subtle 1px dividers & borders
          hover: "#283548",     // Interactive hover state
          subtle: "#161f30",    // Secondary background tint
        },
        // Legacy colors preserved for backward compatibility
        navy: "#0a0e21",
        charcoal: "#111827",
        accentBlue: "#3b82f6",
        accentCyan: "#0ea5e9",
        // Semantic accents
        accent: {
          cyan: "#06b6d4",
          blue: "#3b82f6",
          indigo: "#6366f1",
          purple: "#8b5cf6",
        },
        // Status indicators
        status: {
          emerald: "#10b981",
          amber: "#f59e0b",
          rose: "#ef4444",
          slate: "#64748b",
        }
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Courier New", "monospace"]
      },
      boxShadow: {
        card: "0 4px 20px -2px rgba(0, 0, 0, 0.4)",
        "card-hover": "0 8px 30px -4px rgba(6, 182, 212, 0.12)",
        glow: "0 0 15px rgba(6, 182, 212, 0.25)",
        "glow-purple": "0 0 15px rgba(139, 92, 246, 0.25)",
        "glow-rose": "0 0 15px rgba(239, 68, 68, 0.25)",
      }
    }
  },
  plugins: []
};
