import { expect, Page, test } from "@playwright/test";
import { openProject, signIn } from "./helpers";

// The tour's last step can anchor to the desktop rail, and the `?` replay
// button lives at its foot. Below 768px the rail is the bottom bar and the
// replay button is in the Menu, which is a different assertion than the one
// this spec makes.
test.skip(({ viewport }) => (viewport?.width ?? 0) < 768, "Desktop shell only");
test.skip(({ javaScriptEnabled }) => !javaScriptEnabled, "The tour is a progressive enhancement");

/** Put the signed-in account back into its first-run state.
 *
 * The acceptance seed marks every fixture user as already onboarded, so that
 * the other specs do not open behind a welcome modal. This spec opts itself
 * back in -- and does so through the same endpoint the UI uses, which is also
 * what makes it safe to re-run across all five browser projects in one server
 * session.
 */
async function patchOnboarding(page: Page, body: Record<string, unknown>) {
  const status = await page.evaluate(async (payload) => {
    const token = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? "";
    const response = await fetch("/api/v1/onboarding", {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(payload),
    });
    return response.status;
  }, body);
  expect(status).toBe(200);
}

async function resetOnboarding(page: Page) {
  await patchOnboarding(page, { seen: false, step: 0 });
}

// Every other spec signs in as these same users and must never open behind
// a welcome box, so whatever happens here, leave them onboarded.
test.afterEach(async ({ page }) => {
  if (!page.url().startsWith("http")) return;
  await patchOnboarding(page, { seen: true, step: 0 }).catch(() => undefined);
});

/** Hand the signed-in Events head something of their own to do, so the
 *  tour always has a row to point at however many runs came before. */
async function addMyTodo(page: Page) {
  await openProject(page, "E2E-ICC-EVENT");
  await page.locator("#todo-add").getByLabel("What needs doing?").fill(`Tour item ${Date.now()}`);
  await page.locator("#todo-add").getByLabel("Who?").selectOption("me");
  await page.locator("#todo-add").getByRole("button", { name: "Add" }).click();
}

test("first run shows the welcome modal, and declining it does not come back", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  await resetOnboarding(page);
  await page.goto("/");

  const modal = page.getByRole("dialog", { name: /your work, on one page/i });
  await expect(modal).toBeVisible();
  await expect(modal).toContainText("Approve takes one press");

  await modal.getByRole("button", { name: /no thanks/i }).click();
  await expect(modal).toBeHidden();

  // Persisted server-side, not in sessionStorage: a full reload must not
  // bring it back.
  await page.reload();
  await expect(page.getByRole("dialog", { name: /your work, on one page/i })).toBeHidden();
});

test("the tour is three steps on My work, Esc ends it, and it can be replayed", async ({ page }) => {
  await signIn(page, "e2e_events");
  await addMyTodo(page);
  await resetOnboarding(page);
  await page.goto("/");

  await page.getByRole("dialog", { name: /your work, on one page/i }).getByRole("button", { name: /show me around/i }).click();

  const first = page.getByRole("dialog", { name: /this is your list/i });
  await expect(first).toBeVisible();
  await expect(first).toContainText("Step 1 of 3");

  // Arrow keys drive the tour as well as the buttons.
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("dialog", { name: /press the circle when it is done/i })).toBeVisible();

  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("dialog", { name: /make a new event/i })).toBeVisible();

  // Esc ends the tour, and the end is persisted.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /make a new event/i })).toBeHidden();
  await page.reload();
  await expect(page.getByRole("dialog", { name: /this is your list/i })).toBeHidden();

  // The `?` at the foot of the rail starts it again from step one.
  await page.getByRole("button", { name: /show me around again/i }).first().click();
  await expect(page.getByRole("dialog", { name: /this is your list/i })).toBeVisible();
  await page.getByRole("button", { name: "Skip" }).click();
});

test("the getting-started list ticks itself from real work and can be hidden", async ({ page }) => {
  await signIn(page, "e2e_media");
  await page.goto("/");
  // Hiding the card is permanent by design, so put it back before asserting
  // on it -- every browser project shares one server and one database.
  await patchOnboarding(page, { signal: "checklist_hidden", value: false });
  await patchOnboarding(page, { signal: "project_opened", value: false });
  await page.goto("/");

  const checklist = page.locator("#onboardingChecklist");
  await expect(checklist).toBeVisible();
  const openTask = checklist.locator("li.onb-task").filter({ hasText: "Open an event" });
  await expect(openTask).not.toHaveClass(/is-done/);

  // Opening an event leaves no row behind, so the page reports it.
  await page.locator("#events-title").locator("xpath=ancestor::section").locator("a.cv-item__link").first().click();
  await page.waitForURL(/\/erp\/projects\//);
  await page.goto("/");
  // Done, or -- if that was the last thing on it -- the card is gone.
  if (await checklist.count()) {
    await expect(checklist.locator("li.onb-task").filter({ hasText: "Open an event" })).toHaveClass(/is-done/);
  }

  await patchOnboarding(page, { signal: "project_opened", value: false });
  await page.goto("/");
  await checklist.getByRole("button", { name: /hide this/i }).click();
  await expect(checklist).toHaveCount(0);
  await page.reload();
  await expect(page.locator("#onboardingChecklist")).toHaveCount(0);
});
