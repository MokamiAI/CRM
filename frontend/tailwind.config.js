/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  // <Button variant="..."> builds these names at runtime (`btn-${variant}`),
  // so Tailwind can't find them in the source and would drop them.
  safelist: ["btn-primary", "btn-secondary", "btn-danger", "btn-ghost"],
  // Compiles every hover: variant inside @media (hover: hover), so a tap on
  // a phone doesn't leave the hover style stuck on until the next tap.
  future: {
    hoverOnlyWhenSupported: true,
  },
  theme: {
    extend: {
      fontFamily: {
        // Bundled via @fontsource-variable/inter (main.jsx), so it also
        // works offline inside the Capacitor app.
        sans: ['"Inter Variable"', "Inter", "ui-sans-serif", "system-ui", "-apple-system", "sans-serif"],
      },
      // Built-in CSS easings are too weak for UI motion. Same values as the
      // --ease-* custom properties in index.css.
      transitionTimingFunction: {
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        "in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
        drawer: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      boxShadow: {
        // Hairline elevation: surfaces read as layered, not floating.
        xs: "0 1px 2px 0 rgb(16 24 40 / 0.04)",
        card: "0 1px 2px 0 rgb(16 24 40 / 0.04), 0 1px 3px 0 rgb(16 24 40 / 0.03)",
        pop: "0 12px 32px -8px rgb(16 24 40 / 0.18), 0 4px 8px -4px rgb(16 24 40 / 0.06)",
      },
    },
  },
  plugins: [],
};
