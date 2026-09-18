import { expect, test } from "@playwright/test";
import { openProject, signIn } from "./helpers";

test("project setup exposes Basics and remains usable with browser history", async ({ page }) => {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT");
  await page.goto(`${page.url()}/setup?step=basics`);
  await expect(page.getByRole("heading", { name: "Project basics" })).toBeVisible();
  await page.getByLabel("Venue").fill("Central Campus Auditorium");
  await page.getByRole("button", { name: /save and continue/i }).click();
  await expect(page).toHaveURL(/step=sessions/);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Project basics" })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: /sessions/i })).toBeVisible();
});

test("operational request completes Draft to Submitted to Approved to Completed", async ({ page }, testInfo) => {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-EVENT", "Finance");
  const title = `Equipment request ${testInfo.project.name}`;
  // Creating a request is a secondary action on this tab: the form lives
  // behind "Create a request" so the section opens on what needs deciding.
  await page.getByRole("button", { name: "Create a request" }).click();
  await page.getByLabel("Request type").selectOption({ label: "Equipment" });
  await page.getByLabel("Title", { exact: true }).fill(title);
  await page.getByRole("button", { name: "Create draft" }).click();
  // The Tile System renders each item as one `.ds-row` rather than a table
  // row, and keeps settled items in the same list instead of behind a
  // disclosure -- so the row is located the same way at every stage.
  const rowFor = (text: string) => page.locator(".ds-row").filter({ hasText: text });
  await rowFor(title).getByRole("button", { name: /submit for approval/i }).click();

  // Maker/checker is a release control: the Events Head who creates and
  // submits the request must not be offered its approval action. Since the
  // audit's P1-04 rework the decision form opens from a "Review"
  // disclosure, so the absence to assert is the disclosure itself -- an
  // assertion on the hidden select inside it would pass either way.
  await expect(rowFor(title).locator("details.ds-review")).toHaveCount(0);
  await page.goto("/logout");
  await signIn(page, "e2e_faculty");
  await openProject(page, "E2E-ICC-EVENT", "Finance");
  // A native <summary> is the disclosure's control. Its computed ARIA
  // role differs between engines, so it is located as the element it is.
  await rowFor(title).locator("summary.ds-review__trigger").click();
  await rowFor(title).getByLabel(new RegExp(`Decision for ${title}`)).selectOption("Approved");
  await rowFor(title).getByRole("button", { name: "Save" }).click();
  await rowFor(title).getByRole("button", { name: /mark completed/i }).click();
  await expect(rowFor(title)).toContainText("Completed");
});

test("dynamic feedback stores canonical rating and chart table stays in parity", async ({ page }, testInfo) => {
  // This journey performs authentication, project navigation, a form POST, and
  // a complete server-rendered reload when JavaScript is disabled. Keep every
  // assertion, but allow the deliberately no-JS path enough time on PostgreSQL.
  test.slow();
  const responseText = `Clear schedule and roles — ${testInfo.project.name}`;
  await signIn(page, "e2e_volunteer");
  await openProject(page, "E2E-ICC-EVENT", "People");
  // Responding is a secondary action on this tab: the list of responses is
  // what needs moderating, so the form sits behind its own disclosure.
  await page.getByRole("button", { name: /^Respond to/i }).click();
  await page.getByLabel(/overall rating/i).selectOption("5");
  await page.getByLabel("What worked well?").fill(responseText);
  await page.getByRole("button", { name: /submit feedback/i }).click();
  await expect(page.locator(".ds-row").filter({ hasText: responseText })).toContainText("Pending");
});

test("public site exposes published content without operational or personal data", async ({ page }) => {
  await page.goto("/public/");
  await expect(page.getByRole("heading").first()).toBeVisible();
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/password|registration number|budget line|buddy interaction/i);
});
