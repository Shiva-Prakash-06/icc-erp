import { animate } from "framer-motion/dom";

type Command = {
  name: string;
  url: string;
  category: string;
  keywords?: string;
};

function icon(name: string) {
  const element = document.createElement("i");
  element.className = `ph ${name}`;
  element.setAttribute("aria-hidden", "true");
  return element;
}

export function mountCommandPalette(commands: Command[], initialTrigger: HTMLElement | null) {
  const root = document.getElementById("aurora-command-root");
  if (!root) return;

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let trigger = initialTrigger;
  let active = 0;
  let filtered = commands;

  const scrim = document.createElement("div");
  scrim.className = "command-scrim";
  scrim.setAttribute("role", "presentation");
  scrim.hidden = true;

  const dialog = document.createElement("section");
  dialog.className = "command-dialog";
  dialog.setAttribute("role", "dialog");
  dialog.setAttribute("aria-modal", "true");
  dialog.setAttribute("aria-labelledby", "command-title");

  const header = document.createElement("header");
  header.className = "command-dialog__header";
  const eyebrow = document.createElement("span");
  eyebrow.className = "command-dialog__eyebrow";
  eyebrow.textContent = "Navigation";
  const title = document.createElement("h2");
  title.id = "command-title";
  title.textContent = "Command palette";
  const closeButton = document.createElement("button");
  closeButton.className = "icon-action";
  closeButton.type = "button";
  closeButton.setAttribute("aria-label", "Close command palette");
  closeButton.append(icon("ph-x"));
  header.append(eyebrow, title, closeButton);

  const search = document.createElement("label");
  search.className = "command-search";
  search.append(icon("ph-magnifying-glass"));
  const searchLabel = document.createElement("span");
  searchLabel.className = "sr-only";
  searchLabel.textContent = "Search destinations";
  const input = document.createElement("input");
  input.placeholder = "Search authorized destinations…";
  input.autocomplete = "off";
  input.setAttribute("aria-controls", "command-results");
  const escapeKey = document.createElement("kbd");
  escapeKey.textContent = "Esc";
  search.append(searchLabel, input, escapeKey);

  const results = document.createElement("div");
  results.className = "command-results";
  results.id = "command-results";
  results.setAttribute("role", "listbox");
  results.setAttribute("aria-label", "Destinations");
  dialog.append(header, search, results);
  scrim.append(dialog);
  root.append(scrim);

  function render() {
    results.replaceChildren();
    if (!filtered.length) {
      const empty = document.createElement("div");
      empty.className = "command-empty";
      const message = document.createElement("p");
      message.textContent = `No authorized destination matches “${input.value}”.`;
      empty.append(icon("ph-magnifying-glass"), message);
      results.append(empty);
      input.removeAttribute("aria-activedescendant");
      return;
    }
    filtered.forEach((item, index) => {
      const link = document.createElement("a");
      link.id = `command-${index}`;
      link.href = item.url;
      link.className = `command-result${index === active ? " is-active" : ""}`;
      link.setAttribute("role", "option");
      link.setAttribute("aria-selected", String(index === active));
      const copy = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = item.name;
      const category = document.createElement("small");
      category.textContent = item.category;
      copy.append(name, category);
      link.append(copy, icon("ph-arrow-up-right"));
      link.addEventListener("pointermove", () => {
        if (active !== index) {
          active = index;
          render();
        }
      });
      results.append(link);
    });
    input.setAttribute("aria-activedescendant", `command-${active}`);
  }

  function close() {
    const duration = reduced.matches ? 0 : 0.12;
    const controls = animate(scrim, { opacity: [1, 0] }, { duration });
    void controls.then(() => {
      scrim.hidden = true;
      trigger?.focus();
    });
  }

  function open(nextTrigger: HTMLElement | null) {
    trigger = nextTrigger;
    input.value = "";
    filtered = commands;
    active = 0;
    render();
    scrim.hidden = false;
    const duration = reduced.matches ? 0 : 0.2;
    animate(scrim, { opacity: [0, 1] }, { duration: Math.min(duration, 0.16), ease: "easeOut" });
    animate(dialog, reduced.matches ? { opacity: [0, 1] } : { opacity: [0, 1], y: [-12, 0], scale: [0.98, 1] }, { duration, ease: [0.16, 1, 0.3, 1] });
    window.setTimeout(() => input.focus(), 0);
  }

  input.addEventListener("input", () => {
    const needle = input.value.trim().toLowerCase();
    filtered = needle
      ? commands.filter((item) => `${item.name} ${item.category} ${item.keywords || ""}`.toLowerCase().includes(needle))
      : commands;
    active = 0;
    render();
  });
  closeButton.addEventListener("click", close);
  scrim.addEventListener("pointerdown", (event) => {
    if (event.target === scrim) close();
  });
  dialog.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      active = Math.min(active + 1, Math.max(filtered.length - 1, 0));
      render();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      active = Math.max(active - 1, 0);
      render();
    } else if (event.key === "Enter" && filtered[active]) {
      event.preventDefault();
      window.location.assign(filtered[active].url);
    } else if (event.key === "Tab") {
      event.preventDefault();
      input.focus();
    }
  });

  document.addEventListener("aurora:command-open", (event) => {
    open((event as CustomEvent).detail?.trigger || (document.activeElement as HTMLElement));
  });
  open(initialTrigger);
}
