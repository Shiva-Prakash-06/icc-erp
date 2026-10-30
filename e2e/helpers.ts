import { expect, Page } from "@playwright/test";

export const acceptancePassword = "123";

export async function signIn(page: Page, username: string) {
  // Each call represents a new authentication boundary, including the
  // maker/checker hand-off inside a single test. Clearing the isolated test
  // context's cookies avoids browser back/forward/session restoration from
  // retaining the prior role after a logout redirect.
  //
  // A response the previous page still had in flight can set the old
  // session cookie again after it has been cleared; the login form's token
  // then no longer matches and the server answers "This form expired". So
  // the whole sign-in is tried a second time when it does not land.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await page.goto("about:blank");
    await page.context().clearCookies();
    await page.goto("/login");
    if (!new URL(page.url()).pathname.endsWith("/login")) {
      await page.goto("/logout");
      continue;
    }
    await page.getByLabel(/username or email/i).fill(username);
    await page.getByLabel(/^password/i).fill(acceptancePassword);
    const landed = await Promise.all([
      page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 10_000 }).then(() => true, () => false),
      page.getByRole("button", { name: /^sign in$/i }).click(),
    ]).then(([ok]) => ok);
    if (landed) break;
  }
  await expect(page.locator("body")).toContainText(username);
}

// The event page is one to-do list and folded cards. Older specs name the
// tab they want; each tab's work now lives on one card.
const CARD_FOR: Record<string, string> = {
  logistics: "todo", finance: "money", documents: "files", people: "people", analytics: "finish",
  todo: "todo", schedule: "schedule", money: "money", files: "files", buddies: "buddies",
  feedback: "feedback", applications: "applications", details: "details", finish: "finish",
};

export async function openProject(page: Page, code: string, card?: string) {
  // Codes are not shown to people any more, but the Events search still
  // matches them, so a test can find its fixture by code.
  await page.goto(`/erp/projects?show=all&q=${encodeURIComponent(code)}`);
  await page.locator("a.cv-item__link").first().click();
  await page.waitForURL(/\/erp\/projects\/[0-9a-f-]{36}/);
  if (!card) return;
  const key = CARD_FOR[card.toLowerCase()] ?? card.toLowerCase();
  const url = new URL(page.url());
  url.search = `?card=${key}`;
  url.hash = `card-${key}`;
  await page.goto(url.toString());
}

/** Open a folded card on the event page by its title. A plain <details>, so
 *  this works the same with JavaScript off. */
export async function openCard(page: Page, title: string) {
  const card = page.locator("details.cv-card").filter({ has: page.locator(".cv-card__title", { hasText: new RegExp(`^${title}$`, "i") }) });
  if (!(await card.evaluate((element) => (element as HTMLDetailsElement).open))) {
    await card.locator("summary").click();
  }
  await expect(card.locator(".cv-card__body")).toBeVisible();
  return card;
}
