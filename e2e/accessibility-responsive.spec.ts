import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { openProject, signIn } from "./helpers";

test("authenticated project state has no automatically detectable WCAG A/AA violations", async ({ page }, testInfo) => {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT", "Delivery");
  if (testInfo.project.name === "javascript-disabled") {
    await expect(page.locator("h1")).toHaveCount(1);
    await expect(page.locator("main#main-content")).toHaveCount(1);
    await expect(page.locator(".aurora-table-scroll:not([tabindex='0'])")).toHaveCount(0);
    await expect(page.locator("select:not([aria-label]):not([aria-labelledby]):not([id])")).toHaveCount(0);
    return;
  }
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(results.violations).toEqual([]);
});

test("layout avoids horizontal page overflow and primary controls meet touch sizing", async ({ page }, testInfo) => {
  await signIn(page, "e2e_events");
  await page.goto("/erp/projects");
  if (testInfo.project.name === "zoom-200") await page.locator("html").evaluate((element) => { (element as HTMLElement).style.zoom = "200%"; });
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  const undersized = await page.locator("a, button, input, select, textarea").evaluateAll((elements) => elements.filter((element) => {
    const style = getComputedStyle(element);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = element.getBoundingClientRect();
    const onScreen = rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
    return onScreen && rect.width > 0 && rect.height > 0 && (rect.width < 44 || rect.height < 44);
  }).map((element) => (element.getAttribute("aria-label") || element.textContent || element.tagName).trim()).slice(0, 10));
  expect(undersized).toEqual([]);
});

test("keyboard command palette restores focus; no-JavaScript navigation remains server complete", async ({ page }, testInfo) => {
  await signIn(page, "e2e_faculty");
  if (testInfo.project.name === "javascript-disabled") {
    await page.goto("/erp/projects/new");
    await expect(page.getByRole("heading", { name: /projects and programs/i })).toBeVisible();
    await page.getByRole("link", { name: /published reports/i }).first().click();
    await expect(page).toHaveURL(/\/reports/);
    return;
  }
  const viewport = page.viewportSize();
  if (viewport && viewport.width < 1024) {
    const trigger = page.getByRole("button", { name: "Open navigation" }).first();
    await trigger.focus();
    await page.keyboard.press("Enter");
    const drawer = page.locator("#mobileNavDrawer");
    await expect(drawer).toHaveAttribute("aria-hidden", "false");
    await page.keyboard.press("Escape");
    await expect(drawer).toHaveAttribute("aria-hidden", "true");
    await expect(trigger).toBeFocused();
    return;
  }
  const trigger = page.getByRole("button", { name: /command palette/i });
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
    await page.goto("/?queue=all");
    const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
    expect(dimensions.scrollWidth, `${width}x${height}`).toBeLessThanOrEqual(dimensions.clientWidth + 1);
  }
});

test("reduced-motion preference suppresses meaningful CSS motion", async ({ page }, testInfo) => {
  if (testInfo.project.name === "reduced-motion") {
    await page.emulateMedia({ reducedMotion: "reduce" });
  }
  await signIn(page, "e2e_faculty");
  await page.goto("/?queue=all");
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
