import { expect, test } from "@playwright/test";

// Matches backend/tests/e2e_server.py, which seeds this tester.
const USERNAME = process.env.PLAYWRIGHT_USERNAME ?? "e2e";
const PASSPHRASE = process.env.PLAYWRIGHT_PASSPHRASE ?? "correct horse battery staple";

// A browser that has never seen the tour.
test.use({ storageState: { cookies: [], origins: [] } });

test("the intro tour opens on a first visit, can be skipped, and stays away", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByLabel("Passphrase", { exact: true }).fill(PASSPHRASE);
  await page.getByRole("button", { name: "Continue" }).click();

  const tour = page.getByRole("dialog", { name: "Welcome to PaySense" });
  await expect(tour).toBeVisible();
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(tour.getByRole("heading", { name: /pay-later buy/i })).toBeVisible();
  await tour.getByRole("button", { name: "Skip" }).click();
  await expect(tour).toBeHidden();

  await page.reload();
  await expect(page.getByRole("heading", { name: /^Hi, / })).toBeVisible();
  await expect(tour).toBeHidden();
});
