import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const PERSONA_CSV = path.resolve(__dirname, "../../../data/personas/budget_conscious.csv");

/** Fail the journey if the browser reports a Content-Security-Policy violation. */
function watchForCspViolations(page: Page): string[] {
  const violations: string[] = [];
  page.on("console", (message) => {
    if (/content security policy|refused to (load|execute|connect)/i.test(message.text())) {
      violations.push(message.text());
    }
  });
  return violations;
}

/** Each browser project signs in as its own seeded tester, so parallel runs keep separate ledgers. */
async function signIn(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Username").fill(`e2e-${test.info().project.name}`);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /hi, e2e tester/i })).toBeVisible();
}

test("a new tester signs in, imports a persona statement and sees a forecast", async ({ page }) => {
  const violations = watchForCspViolations(page);
  await signIn(page);

  // Nothing imported yet: the forecast is locked and says why.
  await expect(page.getByText(/unlocks with four months/i)).toBeVisible();

  await page.getByRole("link", { name: "Import" }).first().click();
  await expect(page).toHaveURL(/\/import/);
  await page.getByLabel("Choose a CSV file").setInputFiles(PERSONA_CSV);

  const add = page.getByRole("button", { name: /^add \d+ transactions?$/i });
  await expect(add).toBeEnabled();
  await add.click();
  await expect(page.getByText(/transactions added/i)).toBeVisible();

  await page.getByRole("link", { name: /see your dashboard/i }).click();
  await expect(page.getByRole("img", { name: /score \d+ out of 100/i })).toBeVisible();
  await expect(page.getByText("Show the numbers")).toBeVisible();

  expect(violations).toEqual([]);
});

test("every screen loads for a signed-in tester with its own title", async ({ page }) => {
  const violations = watchForCspViolations(page);
  await signIn(page);

  const screens: [string, RegExp][] = [
    ["/transactions", /transactions/i],
    ["/recurring", /recurring items/i],
    ["/plans", /bnpl plans/i],
    ["/import", /import/i],
    ["/model", /about the model/i],
  ];
  for (const [route, heading] of screens) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    await expect(page).toHaveTitle(/· PaySense$/);
  }
  expect(violations).toEqual([]);
});

test("a visitor without a session is sent to the login page", async ({ page }) => {
  await page.goto("/plans");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByLabel("Username")).toBeVisible();
});
