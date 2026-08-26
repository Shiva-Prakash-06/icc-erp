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
  if ((page.viewportSize()?.width || 1440) < 1024) {
    await page.getByRole("button", { name: "Open navigation" }).first().click();
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
  await signIn(page, "e2e_events");
  await page.goto("/erp/projects/new");
  await expect(page.getByRole("heading", { name: /projects and programs/i })).toBeVisible();
  await expect(page.getByLabel("Operating unit")).toHaveValue(/.+/);
  await expect(page.getByLabel("Wing (ICC)").locator("option")).toContainText(["No wing / IGP", "Events"]);
  const uniqueTitle = `Scoped browser project ${testInfo.project.name}`;
  await page.getByLabel("Title").fill(uniqueTitle);
  await page.getByLabel("Start").fill("2026-09-01");
  await page.getByLabel("End").fill("2026-09-01");
  await page.getByLabel("Wing (ICC)").selectOption({ label: "Events" });
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page).toHaveURL(/\/setup\?step=sessions/);
  await expect(page.getByText(uniqueTitle)).toBeVisible();
  expect((await page.request.get("/api/v1/projects")).status()).toBe(200);
  const payload = await (await page.request.get("/api/v1/projects")).json();
  expect(payload.data.every((project: { code?: string }) => project.code !== "E2E-IGP")).toBeTruthy();
});
