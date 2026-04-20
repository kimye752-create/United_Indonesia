import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#eef2f7",
          100: "#d9e2ec",
          200: "#bccedc",
          300: "#8fa9c4",
          400: "#6b8aab",
          500: "#4f6f91",
          600: "#3d5876",
          700: "#334961",
          800: "#2d3f52",
          900: "#1e2d3d",
          950: "#0f1821",
        },
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
