import type { Config } from "tailwindcss";

const config: Config = {
  // lib/ holds ACCENT_CLASS (persona accent classes like bg-plum-500). It
  // must be scanned or rarely-duplicated classes get dropped from the CSS —
  // e.g. Ray's plum dot vanished once how-it-works stopped also referencing
  // bg-plum-500 literally.
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Claude-inspired warm palette
        cream: {
          50: "#FAF9F5",
          100: "#F5F4EE",
          200: "#EDEBE0",
          300: "#DDD9C8",
        },
        ink: {
          900: "#1F1E1B",
          800: "#2A2925",
          700: "#3D3B36",
          600: "#5A5751",
          500: "#7C7870",
          400: "#A8A39A",
          300: "#C9C5BC",
        },
        coral: {
          50: "#FBF1ED",
          100: "#F4DED3",
          400: "#E89B7E",
          500: "#D97757",
          600: "#C2613F",
          700: "#A04A2D",
        },
        sage: {
          400: "#8CA68C",
          500: "#6B8E6B",
          600: "#52735A",
        },
        plum: {
          500: "#8B6B8E",
          600: "#6F5572",
        },
        // Michael (contrarian bear) accent — oxblood.
        oxblood: {
          500: "#9A3B2E",
          600: "#7E2E23",
        },
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        tightest: "-0.04em",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s ease-out forwards",
        shimmer: "shimmer 8s linear infinite",
      },
    },
  },
  plugins: [],
};
export default config;
