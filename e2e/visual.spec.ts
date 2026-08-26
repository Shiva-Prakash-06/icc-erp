import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("approved Aurora desktop and mobile home states remain visually stable", async ({ page }) => {
  // /erp/oversight now redirects into the merged home's full decision
  // queue -- see in-the-operation-checklists-crystalline-dongarra.md
  // Step 2. Snapshots must be regenerated (`--update-snapshots`) after
  // this change and after the opaque-card/font-wiring CSS changes in
  // Step 6/7; the old oversight-*.png baselines no longer apply.
  await signIn(page, "e2e_faculty");
  await page.goto("/?queue=all");
  await expect(page).toHaveScreenshot("home-desktop.png", {
    animations: "disabled",
    fullPage: true,
    maxDiffPixelRatio: 0.03,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page).toHaveScreenshot("home-mobile.png", {
    animations: "disabled",
    fullPage: true,
    maxDiffPixelRatio: 0.03,
  });
});
