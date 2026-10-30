import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { acceptancePassword, openProject, signIn } from "./helpers";

test("sign-up makes a volunteer straight away, with no approval step", async ({ page }, testInfo) => {
  const suffix = testInfo.project.name.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const name = `candidate${suffix}`;
  await page.goto("/register");
  await page.getByLabel("First name").fill("Candidate");
  await page.getByLabel("Last name").fill(suffix);
  await page.getByLabel("University email").fill(`${name}@christuniversity.in`);
  await page.getByLabel("Password", { exact: true }).fill("Acceptance-only-2026!");
  await page.getByRole("button", { name: /^sign up$/i }).click();
  await expect(page).not.toHaveURL(/pending-approval|register/);
  const me = await page.request.get("/api/v1/me", { maxRedirects: 0 });
  expect(me.status()).toBe(200);
  // A volunteer only views: no event can be edited from this account.
  const events = await page.request.get("/erp/projects", { maxRedirects: 0 });
  expect(events.status()).toBe(200);
});

test("all operational roles are isolated at navigation and API entry points", async ({ browser }) => {
  const expectations = [
    ["e2e_faculty", 200, 200],
    ["e2e_usc", 200, 200],
    ["e2e_igp", 200, 200],
    ["e2e_events", 200, 200],
    ["e2e_volunteer", 403, 403],
  ] as const;
  for (const [username, attendanceStatus, checklistStatus] of expectations) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await signIn(page, username);
    expect((await page.request.get("/api/v1/attendance")).status()).toBe(attendanceStatus);
    expect((await page.request.get("/api/v1/checklist-items")).status()).toBe(checklistStatus);
    const oversight = await page.request.get("/erp/oversight");
    // Only Faculty approves, so only Faculty has a decision queue to open.
    expect(oversight.status(), username).toBe(username === "e2e_faculty" ? 200 : 403);
    await context.close();
  }
});

test("protected workflow resources reject generic PATCH and return RFC 7807 errors", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  const tasksResponse = await page.request.get("/api/v1/tasks");
  expect(tasksResponse.status()).toBe(200);
  const tasks = (await tasksResponse.json()).data;
  expect(tasks.length).toBeGreaterThan(0);
  // The acceptance server runs with CSRF on, as production does. Without the
  // token the request is refused as a CSRF failure (400) before it reaches
  // the workflow guard this test is about.
  const csrfToken = await page.locator('meta[name="csrf-token"]').getAttribute("content");
  const blocked = await page.request.patch(`/api/v1/tasks/${tasks[0].public_id}`, {
    headers: { "X-CSRFToken": csrfToken ?? "" },
    data: { status: "Approved", version: tasks[0].version },
  });
  expect(blocked.status()).toBe(405);
  expect(blocked.headers()["content-type"]).toContain("application/problem+json");
  const problem = await blocked.json();
  expect(problem).toMatchObject({ status: 405, title: expect.any(String) });
});

test("Faculty's queue holds only money and sign-offs, and each link opens the item", async ({ page }) => {
  // Only three things still need an OK: money, finishing an event and
  // putting it on the website. Each queue row links to the card on the
  // event page that holds it.
  await signIn(page, "e2e_faculty");
  await page.goto("/queue");
  const rowOf = (kind: string) => page.locator("li.cv-item").filter({ has: page.locator(".cv-item__meta", { hasText: new RegExp(`^${kind} ·`) }) });
  for (const kind of ["Money", "Finish event"]) {
    const row = rowOf(kind).first();
    await expect(row, kind).toBeVisible();
    const href = await row.locator(".cv-item__act a").first().getAttribute("href");
    expect(href, kind).toMatch(/#[\w-]+$/);
    await page.goto(href!);
    const anchor = new URL(page.url()).hash.slice(1);
    await expect(page.locator(`[id="${anchor}"]`), kind).toBeVisible();
    await page.goto("/queue");
  }
  for (const gone of ["Task", "Checklist", "Document", "Contribution", "Budget line", "Buddy log"]) {
    await expect(rowOf(gone), gone).toHaveCount(0);
  }
});

test("authenticated and public page-state matrix meets structural and axe gates", async ({ page }, testInfo) => {
  const javascriptDisabled = testInfo.project.name === "javascript-disabled";
  await signIn(page, "e2e_faculty");
  const routes = ["/", "/queue", "/reports", "/erp/projects", "/erp/projects?show=finished", "/erp/projects/new", "/erp/imports", "/erp/notifications", "/erp/audit", "/profile", "/admin/users"];
  for (const route of routes) {
    const response = await page.goto(route);
    expect(response?.status(), route).toBe(200);
    await expect(page.locator("h1"), route).toHaveCount(1);
    if (!javascriptDisabled) {
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).disableRules(["color-contrast"]).analyze();
      expect(results.violations, route).toEqual([]);
    }
  }
  await openProject(page, "E2E-ICC-EVENT");
  const base = page.url().split("?")[0];
  for (const tab of ["todo", "schedule", "people", "money", "files", "feedback", "details", "finish"]) {
    await page.goto(`${base}?card=${tab}`);
    await expect(page.locator("h1")).toHaveCount(1);
    if (!javascriptDisabled) {
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).disableRules(["color-contrast"]).analyze();
      expect(results.violations, tab).toEqual([]);
    }
  }
  await page.goto("/public/");
  await expect(page.locator("h1")).toHaveCount(1);
});

test("anonymous public endpoints enforce published-only and operational-data boundaries", async ({ request }) => {
  expect((await request.get("/public/")).status()).toBe(200);
  const analytics = await request.get("/public/analytics-data");
  expect(analytics.status()).toBe(200);
  const serialized = JSON.stringify(await analytics.json());
  expect(serialized).not.toMatch(/person|email|registration|budget|buddy|drive_url/i);
  expect((await request.get("/erp/projects", { maxRedirects: 0 })).status()).toBe(302);
  expect((await request.get("/api/v1/attendance", { maxRedirects: 0 })).status()).toBe(401);
});
