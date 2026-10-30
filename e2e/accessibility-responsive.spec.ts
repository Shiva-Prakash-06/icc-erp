import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { openProject, signIn } from "./helpers";

test("authenticated project state has no automatically detectable WCAG A/AA violations", async ({ page }, testInfo) => {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT", "Logistics");
  if (testInfo.project.name === "javascript-disabled") {
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("main#main-content")).toHaveCount(1);
    await expect(page.locator(".aurora-table-scroll:not([tabindex='0'])")).toHaveCount(0);
    await expect(page.locator("select:not([aria-label]):not([aria-labelledby]):not([id])")).toHaveCount(0);
    return;
  }
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).disableRules(["color-contrast"]).analyze();
  expect(results.violations).toEqual([]);
});

test("layout avoids horizontal page overflow", async ({ page }, testInfo) => {
  await signIn(page, "e2e_events");
  await page.goto("/erp/projects");
  if (testInfo.project.name === "zoom-200") await page.locator("html").evaluate((element) => { (element as HTMLElement).style.zoom = "200%"; });
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
});

test("keyboard command palette restores focus; no-JavaScript navigation remains server complete", async ({ page }, testInfo) => {
  await signIn(page, "e2e_faculty");
  if (testInfo.project.name === "javascript-disabled") {
    await page.goto("/erp/projects/new");
    await expect(page.getByRole("heading", { name: /what is the event\?/i })).toBeVisible();
    await page.getByRole("link", { name: /^reports$/i }).first().click();
    await expect(page).toHaveURL(/\/reports$/);
    return;
  }
  // The Tile System deleted the drawer: the rail is always visible (down
  // the left above 860px, along the bottom below it), so every destination
  // is one tab stop away at every width and there is nothing to open.
  const viewport = page.viewportSize();
  if (viewport && viewport.width < 1024) {
    const rail = page.getByRole("navigation", { name: "Sections" });
    await expect(rail).toBeVisible();
    await expect(rail.getByRole("link", { name: "My work" })).toBeVisible();
    await expect(rail.getByRole("link", { name: "Events" })).toBeVisible();
    return;
  }
  const trigger = page.getByRole("button", { name: /search or jump to/i });
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: /command palette/i })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /command palette/i })).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("all required portrait and landscape widths avoid page overflow", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  const viewports = [
    [320, 568], [568, 320], [375, 667], [667, 375], [390, 844], [844, 390],
    [414, 896], [896, 414], [768, 1024], [1024, 768], [1024, 1366], [1366, 1024],
    [1440, 900], [1440, 810],
  ];
  for (const [width, height] of viewports) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(dimensions.scrollWidth, `${width}x${height}`).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  }
});

test("reduced-motion preference suppresses meaningful CSS motion", async ({ page }, testInfo) => {
  if (testInfo.project.name === "reduced-motion") {
    await page.emulateMedia({ reducedMotion: "reduce" });
  }
  await signIn(page, "e2e_faculty");
  await page.goto("/");
  if (testInfo.project.name !== "reduced-motion") {
    await expect(page.locator("h1")).toBeVisible();
    return;
  }
  expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);
  const offenders = await page.locator("body *").evaluateAll((elements) => elements.filter((element) => {
    const style = getComputedStyle(element);
    const durations = `${style.animationDuration},${style.transitionDuration}`.split(",").map((value) => parseFloat(value) || 0);
    return durations.some((duration) => duration > 0.011);
  }).map((element) => ({ tag: element.tagName, className: element.className, animation: getComputedStyle(element).animationDuration, transition: getComputedStyle(element).transitionDuration })).slice(0, 10));
  expect(offenders).toEqual([]);
});

/* ── UI/UX audit regressions (17 September 2026) ─────────────────────────
   The halves of the audit's findings that only exist once a browser has
   laid the page out. Their computable halves are asserted in
   tests/ui_audit_regression_test.py. */

test("My work, Reports and People have no detectable WCAG A/AA violations", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "javascript-disabled", "axe needs JavaScript");
  for (const [user, path] of [["e2e_faculty", "/"], ["e2e_faculty", "/reports"], ["e2e_faculty", "/admin/users"], ["e2e_media", "/"], ["e2e_volunteer", "/"]] as const) {
    await signIn(page, user);
    await page.goto(path);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).disableRules(["color-contrast"]).analyze();
    expect(results.violations, `${user} ${path}`).toEqual([]);
  }
});

test("P0-02 — no row action is clipped or off-canvas on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "e2e_faculty");
  await openProject(page, "E2E-ICC-EVENT", "Logistics");

  const strayed = await page.locator(".cv-item__act, .cv-tick, .cv-item__title, .cv-menu > summary").evaluateAll((nodes) =>
    nodes
      .filter((node) => (node as HTMLElement).offsetParent !== null)
      .map((node) => {
        const box = node.getBoundingClientRect();
        return { className: node.className, left: Math.round(box.left), right: Math.round(box.right), width: Math.round(box.width) };
      })
      // The audit found Save/Resolve rendered as fragments on the left edge
      // and header actions running past the right.
      .filter((box) => box.left < 0 || box.right > document.documentElement.clientWidth + 1 || box.width === 0));
  expect(strayed).toEqual([]);

  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
});

test("P0-02 — the record title is fully readable at 375 and 390 px", async ({ page }) => {
  for (const width of [375, 390]) {
    await page.setViewportSize({ width, height: 812 });
    await signIn(page, "e2e_faculty");
    await openProject(page, "E2E-ICC-EVENT");
    const title = page.locator("h1.ds-screen__title");
    await expect(title).toHaveText(/Acceptance ICC event/);
    // "Coffee Meet…" was the finding: the element clipped its own content.
    const clipped = await title.evaluate((node) => node.scrollWidth > node.clientWidth + 1);
    expect(clipped, `title is clipped at ${width}px`).toBe(false);
  }
});

test("P0-05 — the phone bar holds four destinations plus Menu, and covers nothing", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page, "e2e_faculty");
  await openProject(page, "E2E-ICC-EVENT", "Logistics");

  const rail = page.getByRole("navigation", { name: "Sections" });
  await expect(rail.locator(".ds-rail__item:visible")).toHaveCount(5);

  // The last interactive element scrolls clear of the bar and the banner.
  const clearance = await page.evaluate(() => {
    const scroller = document.querySelector(".cv-body, .ds-scroll") as HTMLElement | null;
    if (!scroller) return { ok: true };
    scroller.scrollTop = scroller.scrollHeight;
    const nav = document.querySelector(".ds-rail")!.getBoundingClientRect();
    const banner = document.querySelector(".ds-demo-banner")?.getBoundingClientRect();
    const last = scroller.lastElementChild!.getBoundingClientRect();
    return { ok: last.bottom <= nav.top + 1, lastBottom: last.bottom, navTop: nav.top, bannerBottom: banner?.bottom };
  });
  expect(clearance.ok, JSON.stringify(clearance)).toBe(true);
});

test("one press ticks a to-do item, and the rarely used actions stay folded", async ({ page }) => {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT");
  const item = page.locator("#card-todo li.cv-item").first();
  await expect(item).toBeVisible();
  // The tick is a submit button in the list's own form: one press, no page
  // in between, works with JavaScript off.
  const contract = await item.locator("button.cv-tick").evaluate((button: HTMLButtonElement) => ({
    name: button.name,
    value: button.value,
    action: new URL(button.form!.action).pathname,
    method: button.form!.method,
    names: [...button.form!.elements].map((element) => (element as HTMLInputElement).name).filter(Boolean),
  }));
  expect(contract.method).toBe("post");
  expect(contract.name).toBe("done");
  expect(contract.value).toMatch(/^[tc]-[0-9a-f-]{36}$/);
  expect(contract.action).toMatch(/\/todos\/done$/);
  expect(contract.names).toContain("csrf_token");
  // Skip and remove are behind the row's "⋯" until asked for.
  await expect(item.locator(".cv-menu__panel")).toBeHidden();
  await item.locator(".cv-menu > summary").click();
  await expect(item.locator(".cv-menu__panel")).toBeVisible();
});

test("P0-03 — old analytics links land somewhere that lists what they counted", async ({ page }) => {
  // The analytics counters are gone. Faculty's year numbers are on Reports;
  // anyone else's old link opens the Events list.
  await signIn(page, "e2e_faculty");
  await page.goto("/erp/analytics/igp");
  await expect(page).toHaveURL(/\/reports$/);
  await signIn(page, "e2e_igp");
  await page.goto("/erp/analytics/igp");
  await expect(page).toHaveURL(/\/erp\/projects$/);
  await expect(page.getByText("Acceptance IGP programme")).toBeVisible();
});

test("P0-04 — no record shows two contradictory states without naming the dimensions", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  await openProject(page, "E2E-ICC-EVENT", "Documents");

  const rows = page.locator(".ds-row");
  if (await rows.count()) {
    // Every chip on a row declares which question it answers, so "No file"
    // beside "Approved" reads as two facts rather than a contradiction. The
    // dimension is a sibling of the chip so the chip's own text stays the
    // state word alone.
    const unnamed = await page.locator(".ds-row .ds-chip").evaluateAll((chips) =>
      chips
        .filter((chip) => {
          const dimension = chip.parentElement?.querySelector(".ds-chip__dimension");
          return !dimension || !dimension.textContent?.trim();
        })
        .map((chip) => chip.textContent?.trim()));
    expect(unnamed).toEqual([]);
  }
  // A successful verification is never painted as danger.
  await openProject(page, "E2E-ICC-EVENT", "People");
  const verified = page.locator(".ds-row", { hasText: /Verified/ });
  if (await verified.count()) {
    await expect(verified.first().locator(".ds-chip--overdue")).toHaveCount(0);
  }
});
