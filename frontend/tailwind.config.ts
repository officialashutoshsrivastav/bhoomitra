import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#eef7f1", 100: "#d5ebdc", 200: "#a9d6b8", 300: "#74bb8f", 400: "#3f9d68", 500: "#1f7a4a", 600: "#0f5f3a", 700: "#0b4a2d", 800: "#083621", 900: "#052416" },
        navy: { 700: "#1f2f5c", 800: "#17244a", 900: "#101a36" },
        saffron: "#f28c28",
        earth: "#c9a36b",

        /* Survey-sheet surfaces. The app is a record system, so pages sit on
           paper rather than the usual cool grey, and app chrome sits on ink. */
        paper: { 50: "#fbfaf7", 100: "#f5f2ec", 200: "#eae5da", 300: "#d9d2c4" },
        ink: { 700: "#123024", 800: "#0d2419", 900: "#081810" },
      },

      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "Georgia", "ui-serif", "serif"],
      },

      fontSize: {
        "display-sm": ["2rem", { lineHeight: "1.12", letterSpacing: "-0.018em" }],
        "display-md": ["2.75rem", { lineHeight: "1.06", letterSpacing: "-0.02em" }],
        "display-lg": ["3.75rem", { lineHeight: "1.02", letterSpacing: "-0.022em" }],
        "display-xl": ["4.75rem", { lineHeight: "0.98", letterSpacing: "-0.026em" }],
      },

      boxShadow: {
        card: "0 1px 2px rgba(8,24,16,0.05), 0 4px 16px rgba(8,24,16,0.05)",
        lift: "0 2px 4px rgba(8,24,16,0.06), 0 14px 32px rgba(15,95,58,0.12)",
        inset: "inset 0 1px 0 rgba(255,255,255,0.6)",
        drawer: "0 0 0 100vmax rgba(8,24,16,0.45)",
      },

      backgroundImage: {
        /* Cadastral grid — the fine plot lines of a survey sheet. */
        survey:
          "linear-gradient(rgba(15,95,58,0.055) 1px, transparent 1px), linear-gradient(90deg, rgba(15,95,58,0.055) 1px, transparent 1px)",
        "survey-dark":
          "linear-gradient(rgba(169,214,184,0.07) 1px, transparent 1px), linear-gradient(90deg, rgba(169,214,184,0.07) 1px, transparent 1px)",
      },
      backgroundSize: { survey: "28px 28px", "survey-lg": "56px 56px" },

      transitionTimingFunction: {
        settle: "cubic-bezier(0.16, 0.84, 0.44, 1)",
        survey: "cubic-bezier(0.65, 0.05, 0.36, 1)",
        exit: "cubic-bezier(0.4, 0, 1, 1)",
      },
      transitionDuration: { tap: "120ms", state: "200ms", panel: "320ms", enter: "460ms", draw: "1100ms" },

      keyframes: {
        settleUp: { from: { opacity: "0", transform: "translate3d(0,10px,0)" }, to: { opacity: "1", transform: "none" } },
        settleIn: { from: { opacity: "0", transform: "translate3d(-6px,0,0)" }, to: { opacity: "1", transform: "none" } },
        contour: { from: { transform: "scale(0.2)", opacity: "0.5" }, to: { transform: "scale(1)", opacity: "0" } },
        shimmer: { from: { backgroundPosition: "200% 0" }, to: { backgroundPosition: "-200% 0" } },
        drawIn: { to: { strokeDashoffset: "0" } },
        sweep: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(400%)" } },
        driftSlow: { "0%,100%": { transform: "translate3d(0,0,0) scale(1.06)" }, "50%": { transform: "translate3d(-1.5%,-1%,0) scale(1.09)" } },
      },
      animation: {
        "settle-up": "settleUp 460ms cubic-bezier(0.16,0.84,0.44,1) both",
        "settle-in": "settleIn 320ms cubic-bezier(0.16,0.84,0.44,1) both",
        "draw-in": "drawIn 1100ms cubic-bezier(0.65,0.05,0.36,1) forwards",
        sweep: "sweep 1600ms cubic-bezier(0.65,0.05,0.36,1) infinite",
        "drift-slow": "driftSlow 26s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
