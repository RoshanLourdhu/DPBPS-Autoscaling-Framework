// tailwind.config.cjs
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}"
  ],
  darkMode: "media",
  theme: {
    extend: {
      colors: {
        navy: "#0a0e21",
        charcoal: "#1a1e2c",
        accentBlue: "#1e40af",
        accentCyan: "#0ea5e9"
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["Courier New", "monospace"]
      }
    }
  },
  plugins: []
};
