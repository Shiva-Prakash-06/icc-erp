import { expect, Page, test } from "@playwright/test";
import { signIn } from "./helpers";

// The tour anchors to the desktop top bar (command palette, primary nav) and
// to the `?` replay button that lives in it. Below 768px those are replaced by
// the bottom bar and the drawer, where there is nothing to replay from -- the
// tour degrades to the steps that do have a target, which is a different
// assertion than the one this spec makes.
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

test("first run shows the welcome modal, and declining it does not come back", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  await resetOnboarding(page);
  await page.goto("/");

  const modal = page.getByRole("dialog", { name: /everything waiting on you, on one page/i });
  await expect(modal).toBeVisible();
  await expect(modal).toContainText("approve them in place");

  await modal.getByRole("button", { name: /i'll explore myself/i }).click();
  await expect(modal).toBeHidden();

  // Persisted server-side, not in sessionStorage: a full reload must not
  // bring it back.
  await page.reload();
  await expect(page.getByRole("dialog", { name: /everything waiting on you/i })).toBeHidden();
});

test("the tour advances across pages, skips persist, and ? replays it", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  await resetOnboarding(page);
  await page.goto("/");

  await page.getByRole("button", { name: /show me around/i }).click();

  const card = page.getByRole("dialog", { name: /everything waiting on you is here/i });
  await expect(card).toBeVisible();
  await expect(card).toContainText("Step 1 of 6");

  // Arrow keys drive the tour as well as the buttons.
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("dialog", { name: /the numbers are links/i })).toBeVisible();

  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByRole("dialog", { name: /jump anywhere/i })).toBeVisible();

  // Step 4 lives on a project page. Advancing persists the step first, so the
  // tour resumes itself after the full page load rather than restarting.
  await page.getByRole("button", { name: "Next" }).click();
  await page.waitForURL(/\/erp\/projects\//);
  await expect(page.getByRole("dialog", { name: /a project shows what's blocking it/i })).toBeVisible();
  await expect(page.getByRole("dialog").first()).toContainText("Step 4 of 6");

  // Esc ends the tour, and the end is persisted.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /a project shows what's blocking it/i })).toBeHidden();
  await page.reload();
  await expect(page.getByRole("dialog", { name: /blocking it/i })).toBeHidden();

  // The `?` in the top bar starts it again from step one.
  await page.goto("/");
  await page.getByRole("button", { name: /replay the guided tour/i }).click();
  await expect(page.getByRole("dialog", { name: /everything waiting on you is here/i })).toBeVisible();
  await page.getByRole("button", { name: "Skip" }).click();
});

test("the getting-started checklist tracks real work and can be hidden", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  await page.goto("/");
  // Hiding the card is permanent by design, so put it back before asserting
  // on it -- five browser projects share one server and one database.
  await patchOnboarding(page, { signal: "checklist_hidden", value: false });
  await patchOnboarding(page, { signal: "search_used", value: false });
  await page.goto("/");

  const checklist = page.locator("#onboardingChecklist");
  await expect(checklist).toBeVisible();
  await expect(checklist.getByRole("heading", { name: "Getting started" })).toBeVisible();
  await expect(checklist.getByRole("link", { name: /clear your first decision/i })).toBeVisible();

  // Using the command palette is one of the tasks, and nothing else in the
  // database records it -- the browser reports it.
  const searchTask = checklist.locator("li.onb-task").filter({ hasText: "Jump somewhere with" });
  await expect(searchTask).not.toHaveClass(/is-done/);
  await page.getByRole("button", { name: /command palette/i }).click();
  await page.keyboard.press("Escape");
  await page.goto("/");
  await expect(checklist.locator("li.onb-task").filter({ hasText: "Jump somewhere with" })).toHaveClass(/is-done/);

  await checklist.getByRole("button", { name: /hide this/i }).click();
  await expect(checklist).toHaveCount(0);
  await page.reload();
  await expect(page.locator("#onboardingChecklist")).toHaveCount(0);
});
