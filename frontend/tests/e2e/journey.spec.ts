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
async function signIn(page: Page, journey: string) {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Username").fill(`e2e-${test.info().project.name}-${journey}`);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /hi, e2e tester/i })).toBeVisible();
}

test("a new tester signs in, imports a persona statement and sees a forecast", async ({ page }) => {
  const violations = watchForCspViolations(page);
  await signIn(page, "import");

  // Nothing imported yet: the forecast is locked and says why.
  await expect(page.getByText(/unlocks with four months/i)).toBeVisible();

  await page.getByRole("link", { name: "Import" }).first().click();
  await expect(page).toHaveURL(/\/import/);
  await page.getByLabel("Choose a statement file").setInputFiles(PERSONA_CSV);

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
  await signIn(page, "screens");

  const screens: [string, RegExp][] = [
    ["/transactions", /transactions/i],
    ["/categories", /categories/i],
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

test("a tester checks a purchase, tries the suggestion, adds the plan and reads the saved report", async ({
  page,
}) => {
  test.setTimeout(90_000); // two full checks run the forecast simulations several times
  const violations = watchForCspViolations(page);
  await signIn(page, "risk");

  // history first: the check refuses to give a number without it
  await page.getByRole("link", { name: "Import" }).first().click();
  await page.getByLabel("Choose a statement file").setInputFiles(PERSONA_CSV);
  await page.getByRole("button", { name: /^add \d+ transactions?$/i }).click();
  await expect(page.getByText(/transactions added/i)).toBeVisible();

  await page.goto("/risk");
  await page.getByLabel("What are you buying?").fill("Laptop");
  await page.getByLabel("Number of instalments").fill("2");
  await page.getByLabel(/^price/i).fill("300");
  await page.getByRole("button", { name: "Check this purchase" }).click();

  await expect(page.getByRole("img", { name: /score \d+ out of 100/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your repayment history" })).toBeVisible();
  await expect(page.getByText("Show the numbers")).toBeVisible();

  // an unaffordable purchase comes with a change that works; trying it re-runs the check
  const trySuggestion = page.getByRole("button", { name: "Try this" });
  await expect(trySuggestion).toBeVisible();
  await trySuggestion.click();
  await expect(page.getByRole("img", { name: /score \d+ out of 100, safe/i })).toBeVisible();

  await page.getByRole("button", { name: "Add this as a plan" }).click();
  await expect(page.getByText("Plan added")).toBeVisible();

  await page.getByRole("link", { name: /saved report/i }).click();
  await expect(page).toHaveURL(/\/risk\/[0-9a-f-]{36}/);
  await expect(page.getByRole("heading", { level: 1, name: "Saved risk check" })).toBeVisible();
  await expect(page.getByRole("img", { name: /score \d+ out of 100, safe/i })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try this" })).toHaveCount(0);

  await page.goto("/plans");
  await expect(page.getByRole("heading", { name: "Laptop" })).toBeVisible();
  expect(violations).toEqual([]);
});

test("the transactions page shows where the month went, and picking a category filters the list", async ({
  page,
}) => {
  const violations = watchForCspViolations(page);
  await signIn(page, "spending");
  await page.getByRole("link", { name: "Import" }).first().click();
  await page.getByLabel("Choose a statement file").setInputFiles(PERSONA_CSV);
  await page.getByRole("button", { name: /^add \d+ transactions?$/i }).click();
  await expect(page.getByText(/transactions added/i)).toBeVisible();

  await page.goto("/transactions");
  await expect(page.getByRole("heading", { name: "Spending by category" })).toBeVisible();
  const panel = page.getByRole("complementary", { name: /spending this month/i });
  const first = panel.getByRole("button").first();
  await first.click();
  await expect(first).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Clear filters" }).first()).toBeVisible();

  expect(violations).toEqual([]);
});
