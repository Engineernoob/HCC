/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
        serif: ["var(--font-serif)"],
      },
      colors: {
        ink: {
          0: "var(--ink-0)",
          1: "var(--ink-1)",
          2: "var(--ink-2)",
          3: "var(--ink-3)",
          4: "var(--ink-4)",
          5: "var(--ink-5)",
        },
        console: {
          bright: "var(--text-bright)",
          primary: "var(--text-primary)",
          secondary: "var(--text-secondary)",
          dim: "var(--text-dim)",
          faint: "var(--text-faint)",
          gold: "var(--gold)",
          green: "var(--green)",
          blue: "var(--blue)",
          red: "var(--red)",
          rule: "var(--rule)",
          rule2: "var(--rule-2)",
          rule3: "var(--rule-3)",
        },
      },
      boxShadow: {
        none: "none",
      },
    },
  },
  plugins: [],
};
