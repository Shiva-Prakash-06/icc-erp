const purgecss = require("@fullhuman/postcss-purgecss").default;

module.exports = {
  plugins: [
    purgecss({
      contentFunction: (sourceInputFileName) => sourceInputFileName.endsWith("public.css")
        ? ["./app/templates/public/**/*.html", "./app/static/js/public-charts.js"]
        : ["./app/templates/**/*.html", "./app/static/js/**/*.js", "./frontend/src/**/*.{ts,tsx}"],
      safelist: {
        standard: ["alert-success", "alert-danger", "alert-warning", "alert-info"],
        greedy: [/^aurora-badge--status-/],
      },
      variables: true,
      keyframes: true,
      fontFace: true,
    }),
  ],
};
