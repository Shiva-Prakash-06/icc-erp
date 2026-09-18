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
        // The application bundle deliberately does NOT see
        // templates/public_site/. Those pages load the separately purged
        // public stylesheet above and never link aurora.css, so every rule
        // kept here only because a public template mentioned the class --
        // .page-header, .page-title, .kpi-card, .resource-list,
        // .aurora-breadcrumb, .public-chart-frame and the rest of the
        // marketing furniture -- was dead weight in the app bundle.
        : ["./app/templates/*.html", "./app/templates/auth/**/*.html",
           "./app/templates/dashboard/**/*.html", "./app/templates/erp/**/*.html",
           "./app/static/js/**/*.js", "./frontend/src/**/*.{ts,tsx}", "./app/services/**/*.py"],
      safelist: {
        standard: ["alert-success", "alert-danger", "alert-warning", "alert-info"],
        // Every one of these families is built by interpolation in a
        // template (`ds-chip--{{ state }}`), so the extractor only ever
        // sees the bare prefix and purges the real rule -- the state
        // colour then silently disappears and a row reads as unstyled.
        greedy: [
          /^aurora-badge--status-/,
          /^ds-chip--/,
          /^ds-event--/,
          /^ds-row--/,
          /^ds-tile--/,
          /^ds-chart__seg--/,
          /^ds-chart__key--/,
          /^ds-kpi__value--/,
          /^ds-section--/,
          /^ds-fact--/,
        ],
      },
      variables: true,
      keyframes: true,
      fontFace: true,
    }),
  ],
};
