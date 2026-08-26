import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { acceptancePassword, openProject, signIn } from "./helpers";

test("registration enters pending approval and cannot access authenticated data", async ({ page }, testInfo) => {
  const suffix = testInfo.project.name.replace(/[^a-z0-9]/gi, "").toLowerCase();
  const username = `candidate_${suffix}`;
  await page.goto("/register");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Email").fill(`${username}@example.test`);
  await page.getByLabel("Password", { exact: true }).fill("Acceptance-only-2026!");
  await page.getByLabel("Confirm Password").fill("Acceptance-only-2026!");
  await page.getByLabel("Home Campus").selectOption({ index: 1 });
  await page.getByLabel("Requested Role").selectOption("Volunteer");
  await page.getByRole("button", { name: /submit registration/i }).click();
  await expect(page).toHaveURL(/pending-approval/);
  const protectedResponse = await page.request.get("/api/v1/me", { maxRedirects: 0 });
  expect(protectedResponse.status()).toBe(302);
  expect(protectedResponse.headers().location).toContain("pending-approval");
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
    expect(oversight.status(), username).toBe(["e2e_faculty", "e2e_igp", "e2e_events"].includes(username) ? 200 : 403);
    await context.close();
  }
});

test("protected workflow resources reject generic PATCH and return RFC 7807 errors", async ({ page }) => {
  await signIn(page, "e2e_faculty");
  const tasksResponse = await page.request.get("/api/v1/tasks");
  expect(tasksResponse.status()).toBe(200);
  const tasks = (await tasksResponse.json()).data;
  expect(tasks.length).toBeGreaterThan(0);
  const blocked = await page.request.patch(`/api/v1/tasks/${tasks[0].public_id}`, {
    data: { status: "Approved", version: tasks[0].version },
  });
  expect(blocked.status()).toBe(405);
  expect(blocked.headers()["content-type"]).toContain("application/problem+json");
  const problem = await blocked.json();
  expect(problem).toMatchObject({ status: 405, title: expect.any(String) });
});

test("home decision queue includes every pending category and each review link resolves to its exact item", async ({ page }) => {
  // /erp/oversight now redirects into the merged home's full decision
  // queue (?queue=all) -- see
  // in-the-operation-checklists-crystalline-dongarra.md Step 2. This is
  // also the regression net for the summary-first workspace restructure
  // (Step 8): every kind here must resolve to a row rendered outside any
  // collapsed disclosure.
  await signIn(page, "e2e_faculty");
  await page.goto("/?queue=all");
  const expectedKinds = ["Task", "Checklist", "Document", "Contribution", "Operational request", "Budget line", "Buddy log", "Feedback moderation", "Recruitment", "Report approval"];
  for (const kind of expectedKinds) {
    const row = page.getByRole("row").filter({ has: page.getByText(kind, { exact: true }) }).first();
    await expect(row, kind).toBeVisible();
    const href = await row.getByRole("link", { name: "Review" }).getAttribute("href");
    expect(href, kind).toMatch(/#[0-9a-f-]{36}$/);
    await page.goto(href!);
    const anchor = new URL(page.url()).hash.slice(1);
    await expect(page.locator(`[id="${anchor}"]`), kind).toBeVisible();
    await page.goto("/?queue=all");
  }
});

test("authenticated and public page-state matrix meets structural and axe gates", async ({ page }, testInfo) => {
  const javascriptDisabled = testInfo.project.name === "javascript-disabled";
  await signIn(page, "e2e_faculty");
  const routes = ["/", "/?queue=all", "/erp/projects", "/erp/imports", "/erp/notifications", "/erp/audit", "/profile", "/admin/users"];
  for (const route of routes) {
    const response = await page.goto(route);
    expect(response?.status(), route).toBe(200);
    await expect(page.locator("h1"), route).toHaveCount(1);
    if (!javascriptDisabled) {
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      expect(results.violations, route).toEqual([]);
    }
  }
  await openProject(page, "E2E-ICC-EVENT");
  const base = page.url().split("?")[0];
  for (const tab of ["overview", "people", "delivery", "contributions", "finance", "insights", "resources"]) {
    await page.goto(`${base}?tab=${tab}`);
    await expect(page.locator("h1")).toHaveCount(1);
    if (!javascriptDisabled) {
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
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
