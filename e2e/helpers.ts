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
  // Below 768px the tab bar is replaced by a labelled section <select>
  // (project-workspace.md: no swipe-only tabs), so there is no link to
  // click -- drive the real mobile control instead.
  const sectionSelect = page.locator("#projectTabSelect");
  if (await sectionSelect.isVisible()) {
    await sectionSelect.selectOption({ label: tab });
    await page.waitForURL(new RegExp(`tab=`));
    return;
  }
  const link = page.getByRole("link", { name: new RegExp(`^${tab}$`, "i") }).first();
  // Four sections sit in the tab bar; Contributions, Insights and Resources
  // live behind "More". Their links are always in the DOM (so no-JS
  // navigation and deep links still work) but are hidden until the
  // popover opens.
  if (!(await link.isVisible())) {
    await page.getByRole("button", { name: "More" }).first().click();
    await expect(link).toBeVisible();
  }
  await link.click();
}
