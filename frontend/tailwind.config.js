/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
      colors: {
        bull: "#16a34a", bear: "#dc2626", neutral: "#f59e0b",
        bg: "var(--bg)", card: "var(--card)", line: "var(--line)", fg: "var(--fg)", mute: "var(--mute)",
      },
    },
  },
  plugins: [],
};
