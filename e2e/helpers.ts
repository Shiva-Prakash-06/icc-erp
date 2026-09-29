import { expect, Page } from "@playwright/test";

export const acceptancePassword = "123";

export async function signIn(page: Page, username: string) {
  // Each call represents a new authentication boundary, including the
  // maker/checker hand-off inside a single test. Clearing the isolated test
  // context's cookies avoids browser back/forward/session restoration from
  // retaining the prior role after a logout redirect.
  await page.context().clearCookies();
  await page.goto("/login");
  await page.getByLabel(/username or email/i).fill(username);
  await page.getByLabel(/^password/i).fill(acceptancePassword);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith("/login")),
    page.getByRole("button", { name: /access platform/i }).click(),
  ]);
  await expect(page.locator("body")).toContainText(username);
}

export async function openProject(page: Page, code: string, tab?: string) {
  await page.goto("/erp/projects");
  await page.getByText(code, { exact: true }).first().click();
  if (!tab) return;
  // The Tile System's tab strip is five links with no overflow popover and
  // no mobile <select> -- the strip scrolls horizontally instead, so the
  // link is always present and clickable at every width.
  const link = page.getByRole("link", { name: new RegExp(`^${tab}`, "i") }).first();
  await link.scrollIntoViewIfNeeded();
  await link.click();
  await page.waitForURL(new RegExp("tab="));
}

export async function openSection(page: Page, label: string) {
  // A tab opens on its first section; the others sit behind the section
  // strip's tiles, which are plain links (`?section=`), so this is a real
  // navigation in every project, JavaScript-disabled included.
  const tile = page
    .locator(".ds-sections a.ds-section")
    .filter({ has: page.locator(".ds-section__label", { hasText: new RegExp(`^${label}$`, "i") }) })
    .first();
  await tile.scrollIntoViewIfNeeded();
  await tile.click();
  await page.waitForURL(/[?&]section=/);
}

export async function openDialog(page: Page, linkName: string) {
  // Dialogs are `:target` panels behind a plain link, and they rise in over
  // 0.18s. With JavaScript disabled Playwright's actionability check cannot
  // re-poll an element it first met mid-animation, so a click inside the
  // dialog hangs on "element is not stable". Waiting for the entrance to
  // finish is exact, and a no-op once it has.
  await page.getByRole("link", { name: linkName, exact: true }).click();
  const panel = page.locator(".ds-modal:target .ds-modal__panel");
  await expect(panel).toBeVisible();
  await panel.evaluate((element) => Promise.all(element.getAnimations().map((animation) => animation.finished)));
}
