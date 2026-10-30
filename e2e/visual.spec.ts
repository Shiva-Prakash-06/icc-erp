import { expect, test } from "@playwright/test";
import { signIn } from "./helpers";

test("approved Aurora desktop and mobile home states remain visually stable", async ({ page }) => {
  // My work, as Faculty sees it: the OK list first, then the to-do list.
  // Regenerate with `--update-snapshots` whenever the home page changes.
  await signIn(page, "e2e_faculty");
  await page.goto("/");
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
