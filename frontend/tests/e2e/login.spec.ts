import { expect, test } from "@playwright/test";

// Matches backend/tests/e2e_server.py, which seeds this tester.
const USERNAME = process.env.PLAYWRIGHT_USERNAME ?? "e2e";
const DISPLAY_NAME = process.env.PLAYWRIGHT_DISPLAY_NAME ?? "E2E Tester";

test("a visitor is sent to /login, signs in, and lands on the shell", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Username").fill(USERNAME);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();
  await expect(page.getByText(DISPLAY_NAME, { exact: true }).first()).toBeVisible();
});

test("an unknown username shows an error and stays on /login", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("Username").fill("nobody-here");
  await page.getByRole("button", { name: "Continue" }).click();

  // Next's route announcer is also role="alert", so match on the message.
  await expect(
    page.getByRole("alert").filter({ hasText: "No account with that username." }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("the session survives a reload and ends on log out", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill(USERNAME);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
});
