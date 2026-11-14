import { expect, Locator, Page, test } from "@playwright/test";
import { openProject, signIn } from "./helpers";

/* The click budget, measured from the moment someone has signed in and is
   looking at My work. Typing is free; every press of a button or link
   counts. Anything set up for a test -- an item handed to a team, a money
   request waiting for an OK -- is done first, as another person, and is not
   counted.

     See my work                           0
     Tick a to-do item                     1
     Approve money (Faculty)               1
     Hand in a poster against a Media item 2
     Take attendance on the event day      2
     Create an event                       2 (+ typing)
     Add a money request                   3 (+ typing)

   Every browser project runs against one server and one database, so each
   test makes its own uniquely named rows rather than relying on seeded ones
   still being open. */

function counter() {
  let clicks = 0;
  return {
    async click(target: Locator) {
      clicks += 1;
      await target.click();
    },
    /** A press made in the device's own file picker. */
    picked() {
      clicks += 1;
    },
    get clicks() {
      return clicks;
    },
  };
}

function unique(testInfo: { project: { name: string } }, what: string) {
  return `${what} ${testInfo.project.name} ${Date.now()}`;
}

/** As the Events head, hand a new item on today's event to `who`. */
async function handOut(page: Page, title: string, who: string) {
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-TODAY");
  const form = page.locator("#todo-add");
  await form.getByLabel("What needs doing?").fill(title);
  await form.getByLabel("Who?").selectOption(who);
  // Long overdue, so it leads the Today list however much else is on it.
  await form.getByLabel(/by when/i).fill("2026-01-01");
  await form.getByRole("button", { name: "Add" }).click();
  await expect(page.locator("#card-todo")).toContainText(title);
}

function row(page: Page, text: string) {
  return page.locator("li.cv-item").filter({ hasText: text });
}

test("0 clicks: every role signs in to Campuses, and My work is one press away", async ({ page }) => {
  const landing: [string, RegExp][] = [
    ["e2e_faculty", /needs your ok|to do|caught up/i],
    ["e2e_usc", /to do|today's event|your events|caught up/i],
    ["e2e_events", /to do|today's event/i],
    ["e2e_igp", /to do|your events/i],
    ["e2e_media", /to do/i],
    ["e2e_culturals", /to do/i],
  ];
  for (const [user, heading] of landing) {
    await signIn(page, user, { stayOnLanding: true });
    await expect(page, user).toHaveURL(/\/overview$/);
    await page.getByRole("link", { name: "My work" }).filter({ visible: true }).first().click();
    await expect(page, user).toHaveURL(/\/$/);
    await expect(page.locator("h1"), user).toHaveText("My work");
    await expect(page.locator(".cv-section__title").first(), user).toHaveText(heading);
  }
  // The Media and Culturals heads see their team's items from ICC and IGP
  // events alike, and nothing of anyone else's.
  await signIn(page, "e2e_media");
  await expect(page.locator("main")).toContainText("Acceptance IGP programme");
  await expect(page.locator("main")).not.toContainText("Plan the opening dance");
  await signIn(page, "e2e_culturals");
  await expect(page.locator("main")).toContainText("Run the culture night");
  await expect(page.locator("main")).not.toContainText("Make the event poster");

  // A volunteer opens on the events they are on: when, where, their job.
  await signIn(page, "e2e_volunteer");
  await expect(page.locator("h1")).toHaveText("My activities");
  await expect(row(page, "Acceptance event today")).toContainText("Your job: Usher");
});

test("1 click: tick a to-do item from My work", async ({ page }, testInfo) => {
  const title = unique(testInfo, "Send the minutes");
  await handOut(page, title, "usc");
  await signIn(page, "e2e_usc");
  const budget = counter();
  await budget.click(row(page, title).getByRole("button", { name: /mark .* done/i }));
  await expect(page).toHaveURL(/\/$/);
  await expect(row(page, title)).toHaveCount(0);
  expect(budget.clicks).toBeLessThanOrEqual(1);
});

test("1 click: Faculty approves money from My work", async ({ page }, testInfo) => {
  const whatFor = unique(testInfo, "Bus fare");
  await signIn(page, "e2e_events");
  await openProject(page, "E2E-ICC-TODAY", "money");
  await page.locator("#card-money").getByLabel("What for?").fill(whatFor);
  await page.locator("#card-money").getByLabel("How much (₹)?").fill("300");
  await page.locator("#card-money").getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.locator("#card-money li.cv-item").filter({ hasText: whatFor })).toContainText("Asked");

  await signIn(page, "e2e_faculty");
  const budget = counter();
  await budget.click(row(page, whatFor).getByRole("button", { name: /^approve/i }));
  await expect(page).toHaveURL(/\/$/);
  await expect(row(page, whatFor)).toHaveCount(0);
  expect(budget.clicks).toBeLessThanOrEqual(1);
});

test("2 clicks: the Media head hands in a poster", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "javascript-disabled", "Without JavaScript a Send button is a third press");
  const title = unique(testInfo, "Design the poster");
  await handOut(page, title, "media");
  await signIn(page, "e2e_media");
  const budget = counter();
  const chooser = page.waitForEvent("filechooser");
  await budget.click(row(page, title).getByText("Add file"));
  // Picking the file in the phone's or computer's own picker is the second,
  // and sends it: there is no Save to press.
  await (await chooser).setFiles({ name: "poster.png", mimeType: "image/png", buffer: Buffer.from("89504e470d0a1a0a", "hex") });
  budget.picked();
  await expect(page).toHaveURL(/\/$/);
  await expect(row(page, title)).toHaveCount(0);
  expect(budget.clicks).toBeLessThanOrEqual(2);
});

test("2 clicks: take attendance on the event day", async ({ page }) => {
  await signIn(page, "e2e_events");
  const budget = counter();
  await budget.click(page.getByRole("link", { name: /take attendance.*acceptance event today/i }).first());
  await expect(page.locator("h1")).toHaveText("Who came?");
  await budget.click(page.getByRole("button", { name: "Save attendance" }));
  await expect(page).toHaveURL(/\/$/);
  expect(budget.clicks).toBeLessThanOrEqual(2);
});

test("2 clicks: create an event", async ({ page }, testInfo) => {
  const title = unique(testInfo, "Board games night");
  await signIn(page, "e2e_events");
  const budget = counter();
  await budget.click(page.getByRole("link", { name: /new event/i }).first());
  await page.getByLabel("Name").fill(title);
  await budget.click(page.getByRole("button", { name: "Create event" }));
  await expect(page.locator("h1")).toHaveText(title);
  expect(budget.clicks).toBeLessThanOrEqual(2);
});

test("3 clicks: add a money request", async ({ page }, testInfo) => {
  const whatFor = unique(testInfo, "Paper cups");
  await signIn(page, "e2e_events");
  const budget = counter();
  await budget.click(page.locator("section", { has: page.locator("#events-title") }).locator("a.cv-item__link").first());
  await page.waitForURL(/\/erp\/projects\//);
  const money = page.locator("#card-money");
  await budget.click(money.locator(":scope > summary"));
  await money.getByLabel("What for?").fill(whatFor);
  await money.getByLabel("How much (₹)?").fill("120");
  await budget.click(money.getByRole("button", { name: "Ask", exact: true }));
  const asked = page.locator("#card-money li.cv-item").filter({ hasText: whatFor });
  await expect(asked).toContainText("Asked");
  expect(budget.clicks).toBeLessThanOrEqual(3);
  // Tidy up, so Faculty's OK list does not grow with every run.
  await asked.getByRole("button", { name: "Remove" }).click();
  await expect(page.locator("#card-money li.cv-item").filter({ hasText: whatFor })).toHaveCount(0);
});
