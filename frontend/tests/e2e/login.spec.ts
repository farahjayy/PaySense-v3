import { expect, test } from "@playwright/test";

// Matches backend/tests/e2e_server.py, which seeds this tester.
const USERNAME = process.env.PLAYWRIGHT_USERNAME ?? "e2e";
const DISPLAY_NAME = process.env.PLAYWRIGHT_DISPLAY_NAME ?? "E2E Tester";
// Every seeded browser-test account shares this passphrase (test tooling only, D-49).
const PASSPHRASE = process.env.PLAYWRIGHT_PASSPHRASE ?? "correct horse battery staple";

test("a visitor is sent to /login, signs in, and lands on the shell", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Username").fill(USERNAME);
  await page.getByLabel("Passphrase", { exact: true }).fill(PASSPHRASE);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();
  await expect(page.getByText(DISPLAY_NAME, { exact: true }).first()).toBeVisible();
});

test("a wrong passphrase shows one generic error and stays on /login", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("Username").fill(USERNAME);
  await page.getByLabel("Passphrase", { exact: true }).fill("not the right passphrase");
  await page.getByRole("button", { name: "Continue" }).click();

  // Next's route announcer is also role="alert", so match on the message.
  await expect(
    page.getByRole("alert").filter({ hasText: "That username and passphrase do not match." }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("the session survives a reload and ends on log out", async ({ page }) => {
  // its own account: logging out revokes every session of that user (D-49)
  await page.goto("/login");
  await page.getByLabel("Username").fill(`e2e-${test.info().project.name}-logout`);
  await page.getByLabel("Passphrase", { exact: true }).fill(PASSPHRASE);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();

  // on a phone the profile, and with it Log out, is under More
  if (test.info().project.name === "phone") await page.getByRole("button", { name: "More" }).click();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});
