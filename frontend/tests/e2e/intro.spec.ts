import { expect, test } from "@playwright/test";

// Matches backend/tests/e2e_server.py, which seeds this tester (notice already accepted).
const USERNAME = process.env.PLAYWRIGHT_USERNAME ?? "e2e";
const PASSPHRASE = process.env.PLAYWRIGHT_PASSPHRASE ?? "correct horse battery staple";

// A browser that has never seen the intro.
test.use({ storageState: { cookies: [], origins: [] } });

test("onboarding and the tour open on a first visit, can be skipped, stay away, and replay", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email or username").fill(USERNAME);
  await page.getByLabel("Password", { exact: true }).fill(PASSPHRASE);
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();

  const onboarding = page.getByRole("region", { name: "Getting to know PaySense" });
  await expect(onboarding).toBeVisible();
  await onboarding.getByRole("button", { name: "Next" }).click();
  await expect(onboarding.getByRole("heading", { name: /pay-later buy/i })).toBeVisible();
  await onboarding.getByRole("button", { name: "Skip" }).click();
  await expect(onboarding).toBeHidden();
  await expect(page.getByRole("heading", { name: /^Hi, / })).toBeVisible();

  // Then the tour of the app itself points at the real controls, one at a time.
  const tour = page.getByRole("dialog", { name: "Tour of PaySense" });
  await expect(tour.getByRole("heading", { name: "Where your money is heading" })).toBeVisible();
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(tour.getByRole("heading", { name: "Start here" })).toBeVisible();
  await tour.getByRole("button", { name: "Skip tour" }).click();
  await expect(tour).toBeHidden();

  await page.reload();
  await expect(page.getByRole("heading", { name: /^Hi, / })).toBeVisible();
  await expect(onboarding).toBeHidden();

  test.skip(test.info().project.name === "phone", "the replay sits in the sidebar profile here");
  await page.getByRole("button", { name: "Show the intro again" }).first().click();
  const replay = page.getByRole("dialog", { name: "Welcome to PaySense" });
  await expect(replay).toBeVisible();
  await replay.getByRole("button", { name: "Close" }).click();
  await expect(replay).toBeHidden();
});
