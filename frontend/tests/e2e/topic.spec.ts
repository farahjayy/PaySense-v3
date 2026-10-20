import { expect, test, type Page } from "@playwright/test";

const PASSPHRASE = "correct horse battery staple";

async function signIn(page: Page, journey: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(`e2e-${test.info().project.name}-${journey}`);
  await page.getByLabel("Passphrase", { exact: true }).fill(PASSPHRASE);
  await page.getByRole("button", { name: "Continue" }).click();
}

test("first login shows the privacy notice, which must be accepted before the app", async ({
  page,
}) => {
  await signIn(page, "consent");
  const onboarding = page.getByRole("region", { name: "Getting to know PaySense" });
  await expect(onboarding.getByRole("heading", { name: "Before you start" })).toBeVisible();
  await expect(onboarding.getByRole("listitem").filter({ hasText: "What the assistant sends" })).toBeVisible();
  await onboarding.getByRole("button", { name: /i understand/i }).click();
  await onboarding.getByRole("link", { name: "Go to the dashboard" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /hi, e2e tester/i })).toBeVisible();
  await page.goto("/account");
  await expect(page.getByText(/You accepted version v2/)).toBeVisible();
});

test("set a budget, add an expense, the bar moves, and the over-budget alert appears", async ({
  page,
}) => {
  await signIn(page, "budgets");
  await expect(page.getByRole("heading", { level: 1, name: /hi, e2e tester/i })).toBeVisible();

  await page.goto("/budgets");
  await expect(page.getByRole("heading", { level: 1, name: "Budgets" })).toBeVisible();
  await expect(page.getByText("No budgets yet")).toBeVisible();
  await page.getByLabel("Category").selectOption("Food");
  await page.getByLabel(/monthly limit/i).fill("50");
  await page.getByRole("button", { name: "Add budget" }).click();
  const bar = page.getByRole("progressbar", { name: "Food spent" });
  await expect(bar).toHaveAttribute("aria-valuenow", "0");

  // an expense today (the e2e server's "today" is 29 December 2025)
  await page.goto("/transactions");
  await page.getByRole("button", { name: /add transaction/i }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Date").fill("2025-12-29");
  await dialog.getByLabel("Amount").fill("60");
  await dialog.getByLabel("Category").selectOption("Food");
  await dialog.getByRole("button", { name: "Add transaction" }).click();
  await expect(dialog).toBeHidden();

  await page.goto("/budgets");
  await expect(page.getByRole("progressbar", { name: "Food spent" })).toHaveAttribute(
    "aria-valuenow",
    "100",
  );
  await expect(page.getByText("Over the limit")).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Needs your attention")).toBeVisible();
  await expect(page.getByText("Food is over budget.")).toBeVisible();
});
