import { expect, test } from "@playwright/test";
import { openCard, openProject, signIn } from "./helpers";

test("event details are edited in place and the page comes back to them", async ({ page }) => {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT");
  const card = await openCard(page, "Event details");
  await card.getByLabel("Where").fill("Central Campus Auditorium");
  await card.getByRole("button", { name: "Save" }).click();
  await expect(page).toHaveURL(/card=details/);
  await expect(page.locator("#card-details")).toHaveAttribute("open", "");
  await expect(page.locator("#card-details").getByLabel("Where")).toHaveValue("Central Campus Auditorium");
  // The retired setup wizard's links still land somewhere useful.
  await page.goto(`${page.url().split("?")[0]}/setup?step=basics`);
  await expect(page).toHaveURL(/card=details/);
});

test("money is asked for, approved by Faculty, then marked paid", async ({ page }, testInfo) => {
  const whatFor = `Banner printing ${testInfo.project.name} ${Date.now()}`;
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT", "Money");
  const money = page.locator("#card-money");
  await money.getByLabel("What for?").fill(whatFor);
  await money.getByLabel("How much (₹)?").fill("750");
  await money.getByRole("button", { name: "Ask", exact: true }).click();
  const row = page.locator("#card-money li.cv-item").filter({ hasText: whatFor });
  await expect(row).toContainText("Asked");
  // The person who asked is never offered the approval.
  await expect(row.getByRole("button", { name: "Approve" })).toHaveCount(0);

  await signIn(page, "e2e_faculty");
  await page.goto("/queue");
  const queued = page.locator("li.cv-item").filter({ hasText: whatFor });
  await queued.getByRole("button", { name: /^Approve/ }).click();
  await expect(page).toHaveURL(/\/queue$/);
  await expect(page.locator("li.cv-item").filter({ hasText: whatFor })).toHaveCount(0);

  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT", "Money");
  const approved = page.locator("#card-money li.cv-item").filter({ hasText: whatFor });
  await expect(approved).toContainText("Approved");
  await approved.getByRole("button", { name: "Mark paid" }).click();
  await expect(page.locator("#card-money li.cv-item").filter({ hasText: whatFor })).toContainText("Paid");
});

test("a feedback link is answered without signing in", async ({ page, browser }, testInfo) => {
  test.slow();
  const answer = `Clear schedule and roles — ${testInfo.project.name}`;
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT", "Feedback");
  const card = page.locator("#card-feedback");
  if (await card.getByRole("button", { name: "Make feedback link" }).count()) {
    await card.getByRole("button", { name: "Make feedback link" }).click();
  }
  const link = await page.locator("#feedback-link").inputValue();
  expect(link).toMatch(/\/public\/feedback\/[\w-]+$/);

  const visitor = await browser.newContext({ javaScriptEnabled: testInfo.project.name !== "javascript-disabled" });
  const stranger = await visitor.newPage();
  await stranger.goto(new URL(link).pathname);
  await stranger.getByRole("radio", { name: "5" }).check();
  await stranger.locator("textarea").first().fill(answer);
  await stranger.getByRole("button", { name: "Send" }).click();
  await expect(stranger.getByText(/thank you/i)).toBeVisible();
  await visitor.close();

  await page.reload();
  await expect(page.locator("#card-feedback")).toContainText(answer);
});

test("public site exposes published content without operational or personal data", async ({ page }) => {
  await page.goto("/public/");
  await expect(page.getByRole("heading").first()).toBeVisible();
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/password|registration number|budget line|buddy interaction/i);
});
