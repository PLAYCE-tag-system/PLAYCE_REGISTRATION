/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./qr.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#080B10",
          900: "#10151F",
          800: "#17202C",
          700: "#202B3A",
        },
        brand: {
          300: "#7DD3FC",
          400: "#38BDF8",
          500: "#0EA5E9",
        },
        mint: "#5EEAD4",
        danger: "#FB7185",
      },
      boxShadow: {
        glow: "0 0 36px rgba(56, 189, 248, 0.18)",
      },
    },
  },
  plugins: [],
};
