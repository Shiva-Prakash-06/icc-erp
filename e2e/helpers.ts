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
