import { animate } from "framer-motion/dom";

export function animateShellEvent(event: Event) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const custom = event as CustomEvent<{ open?: boolean }>;

  if (event.type === "oia:rail-change") {
    document.querySelectorAll<HTMLElement>(".app-nav-link i, .brand-mark").forEach((item, index) => {
      animate(item, { opacity: [0.72, 1], scale: [0.94, 1] }, { duration: 0.2, delay: Math.min(index, 7) * 0.018, ease: [0.16, 1, 0.3, 1] });
    });
  }

  if (event.type === "oia:notification-change" && custom.detail?.open) {
    const panel = document.getElementById("notificationPanel");
    if (panel) animate(panel, { opacity: [0, 1], x: [24, 0], scale: [0.98, 1] }, { duration: 0.24, ease: [0.16, 1, 0.3, 1] });
  }

  if (event.type === "oia:project-view-change") {
    const active = document.querySelector<HTMLElement>("[data-project-view-panel].is-active");
    if (active) animate(active, { opacity: [0, 1], y: [8, 0] }, { duration: 0.24, ease: [0.16, 1, 0.3, 1] });
  }
}

