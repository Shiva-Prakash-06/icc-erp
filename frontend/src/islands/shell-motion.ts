function play(element: HTMLElement, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
  element.animate(keyframes, { fill: "both", ...options });
}

export function animateShellEvent(event: Event) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const custom = event as CustomEvent<{ open?: boolean }>;

  if (event.type === "oia:rail-change") {
    document.querySelectorAll<HTMLElement>(".app-nav-link i, .brand-mark").forEach((item, index) => {
      play(item, [{ opacity: 0.72, transform: "scale(.94)" }, { opacity: 1, transform: "scale(1)" }], { duration: 200, delay: Math.min(index, 7) * 18, easing: "cubic-bezier(.16,1,.3,1)" });
    });
  }

  if (event.type === "oia:notification-change" && custom.detail?.open) {
    const panel = document.getElementById("notificationPanel");
    if (panel) play(panel, [{ opacity: 0, transform: "translateX(24px) scale(.98)" }, { opacity: 1, transform: "none" }], { duration: 240, easing: "cubic-bezier(.16,1,.3,1)" });
  }

  if (event.type === "oia:project-view-change") {
    const active = document.querySelector<HTMLElement>("[data-project-view-panel].is-active");
    if (active) play(active, [{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 240, easing: "cubic-bezier(.16,1,.3,1)" });
  }
}
