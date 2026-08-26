import "../aurora.css";

type Command = {
  name: string;
  url: string;
  category: string;
  keywords?: string;
};

function readCommands(): Command[] {
  const source = document.getElementById("aurora-command-data");
  if (!source?.textContent) return [];
  try {
    const parsed = JSON.parse(source.textContent);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

let commandRuntime: Promise<typeof import("../islands/command-palette")> | null = null;

function loadCommandPalette(event: Event) {
  if (!document.getElementById("aurora-command-root")) return;
  document.removeEventListener("aurora:command-open", loadCommandPalette);
  const trigger = (event as CustomEvent).detail?.trigger as HTMLElement | undefined;
  commandRuntime ??= import("../islands/command-palette");
  void commandRuntime.then(({ mountCommandPalette }) => {
    mountCommandPalette(readCommands(), trigger || null);
  });
}

document.addEventListener("aurora:command-open", loadCommandPalette);

let shellMotionRuntime: Promise<typeof import("../islands/shell-motion")> | null = null;
function loadShellMotion(event: Event) {
  shellMotionRuntime ??= import("../islands/shell-motion");
  void shellMotionRuntime.then(({ animateShellEvent }) => animateShellEvent(event));
}
document.addEventListener("oia:rail-change", loadShellMotion);
document.addEventListener("oia:notification-change", loadShellMotion);
document.addEventListener("oia:project-view-change", loadShellMotion);
document.documentElement.classList.add("has-aurora-runtime");
