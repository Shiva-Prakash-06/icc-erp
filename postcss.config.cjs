const purgecss = require("@fullhuman/postcss-purgecss").default;

module.exports = {
  plugins: [
    purgecss({
      contentFunction: (sourceInputFileName) => sourceInputFileName.endsWith("public.css")
        // The public templates live in templates/public_site/, not
        // templates/public/ -- the old glob matched nothing, so every class
        // selector was purged and the public site rendered unstyled.
        ? ["./app/templates/public_site/**/*.html", "./app/static/js/public-charts.js"]
        // app/services is in scope because NAV_REGISTRY names its own
        // ph-* icon classes in Python: without it, any icon used only by
        // the nav (ph-gauge, ph-buildings) was purged and rendered as a
        // solid square, since .ph paints currentColor through a mask that
        // no longer had a --oia-icon URL.
        : ["./app/templates/**/*.html", "./app/static/js/**/*.js", "./frontend/src/**/*.{ts,tsx}", "./app/services/**/*.py"],
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
