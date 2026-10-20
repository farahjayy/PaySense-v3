import { expect, test } from "@playwright/test";

// Matches backend/tests/e2e_server.py, which seeds this tester.
const USERNAME = process.env.PLAYWRIGHT_USERNAME ?? "e2e";
const DISPLAY_NAME = process.env.PLAYWRIGHT_DISPLAY_NAME ?? "E2E Tester";
// Every seeded browser-test account shares this passphrase (test tooling only, D-49).
const PASSPHRASE = process.env.PLAYWRIGHT_PASSPHRASE ?? "correct horse battery staple";

test("a visitor lands on /welcome, goes on to /login, signs in, and lands on the shell", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
  await expect(page.getByRole("heading", { level: 1, name: /think before you split/i })).toBeVisible();
  await page.getByRole("link", { name: "Get started" }).first().click();
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email or username").fill(USERNAME);
  await page.getByLabel("Password", { exact: true }).fill(PASSPHRASE);
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();
  // the sidebar's profile card; on a phone it is inside More
  if (test.info().project.name === "desktop") {
    await expect(page.getByText(DISPLAY_NAME, { exact: true }).first()).toBeVisible();
  }
});

test("a wrong passphrase shows one generic error and stays on /login", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("Email or username").fill(USERNAME);
  await page.getByLabel("Password", { exact: true }).fill("not the right passphrase");
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();

  // Next's route announcer is also role="alert", so match on the message.
  await expect(
    page.getByRole("alert").filter({ hasText: "That email or username and password do not match." }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("the session survives a reload and ends on log out", async ({ page }) => {
  // its own account: logging out revokes every session of that user (D-49)
  await page.goto("/login");
  await page.getByLabel("Email or username").fill(`e2e-${test.info().project.name}-logout`);
  await page.getByLabel("Password", { exact: true }).fill(PASSPHRASE);
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: `Hi, ${DISPLAY_NAME}` })).toBeVisible();

  // on a phone the profile, and with it Log out, is under More
  if (test.info().project.name === "phone") await page.getByRole("button", { name: "More" }).click();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/welcome$/);

  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
});

test("a new student creates an account from the welcome page and lands in onboarding", async ({
  page,
}) => {
  // unique per run: the e2e server keeps its accounts until it restarts
  const email = `new-${test.info().project.name}-${Date.now()}@example.com`;
  await page.goto("/welcome");
  await page.getByRole("link", { name: /create your account/i }).click();
  await expect(page).toHaveURL(/\/login#signup$/);
  await expect(page.getByRole("heading", { level: 1, name: "Create your account" })).toBeVisible();

  await page.getByLabel("Your name").fill("Nur");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page.getByLabel("Password", { exact: true }).fill(PASSPHRASE);
  await page.locator("form").getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("region", { name: "Getting to know PaySense" })).toBeVisible();
});
