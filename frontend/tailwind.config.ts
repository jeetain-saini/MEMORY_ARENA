import type { Config } from "tailwindcss";

// MemoryArena — Tailwind configuration.
// Stage 0: content globs target the App Router structure; design tokens (theme)
// will be filled in alongside shadcn/ui setup in Stage 4.
const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
