import { expect, test } from "@playwright/test";
import { acceptancePassword, signIn } from "./helpers";

test("authentication handles invalid login, valid login, logout, and session purge", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/username or email/i).fill("e2e_faculty");
  await page.getByLabel(/^password/i).fill("wrong-password");
  await page.getByRole("button", { name: /access platform/i }).click();
  await expect(page.getByRole("alert")).toContainText(/invalid/i);

  await page.getByLabel(/username or email/i).fill("e2e_faculty");
  await page.getByLabel(/^password/i).fill(acceptancePassword);
  await page.getByRole("button", { name: /access platform/i }).click();
  await expect(page).toHaveURL("http://127.0.0.1:5010/");
  // The phone bar carries four destinations plus Menu (audit P0-05), so
  // below 860px sign-out lives in the Menu drawer rather than as a ninth
  // icon on the bar. Opening it is part of what this test proves: every
  // destination the bar dropped is still one tap away.
  const viewport = page.viewportSize();
  if (viewport && viewport.width <= 860) {
    await page.locator("summary.ds-menu__trigger").click();
    await expect(page.locator(".ds-menu__drawer")).toBeVisible();
  }
  await page.getByRole("link", { name: /log out/i }).first().click();
  await expect(page).toHaveURL(/\/login/);
  const response = await page.request.get("/api/v1/me");
  expect(response.status()).toBe(401);
});

test("role-shaped navigation and APIs do not leak forbidden operations", async ({ page }) => {
  await signIn(page, "e2e_volunteer");
  await expect(page.getByRole("link", { name: "Oversight", exact: true })).toHaveCount(0);
  expect((await page.request.get("/api/v1/attendance")).status()).toBe(403);
  expect((await page.request.get("/api/v1/checklist-items")).status()).toBe(403);
  expect((await page.request.get("/erp/oversight")).status()).toBe(403);
});

test("scoped ICC Events Head reaches project creation but cannot see IGP", async ({ page }, testInfo) => {
  // Creation moved from an inline campus/program/year/wing form on the
  // projects list to the "Create a project" page, where campus, academic
  // year, owner, code and status are all inferred from the actor's own
  // scope. What still has to hold is the boundary: an ICC Events Head can
  // create, is never offered IGP, and never sees the IGP project.
  await signIn(page, "e2e_events");
  await page.goto("/erp/projects/new");
  await expect(page.getByRole("heading", { name: /create a project/i })).toBeVisible();
  const manual = page.locator("form", { has: page.locator("#manual_title") });
  const programs = manual.getByLabel("Program");
  await expect(programs.locator("option")).toContainText(["ICC"]);
  await expect(programs.locator("option").filter({ hasText: "IGP" })).toHaveCount(0);

  const uniqueTitle = `Scoped browser project ${testInfo.project.name}`;
  await manual.locator("#manual_title").fill(uniqueTitle);
  await manual.locator("#manual_start").fill("2026-09-01");
  await manual.locator("#manual_end").fill("2026-09-01");
  await manual.getByRole("button", { name: "Create project" }).click();
  await expect(page.getByText(uniqueTitle)).toBeVisible();

  expect((await page.request.get("/api/v1/projects")).status()).toBe(200);
  const payload = await (await page.request.get("/api/v1/projects")).json();
  expect(payload.data.every((project: { code?: string }) => project.code !== "E2E-IGP")).toBeTruthy();
});