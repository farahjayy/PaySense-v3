import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { ACCOUNT_FILE } from "../../playwright.real.config";

type Account = { username: string; passphrase: string | null; csv: string };

test("on the real database and model: login, import, forecast, check, confirm, saved report", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const account = JSON.parse(readFileSync(ACCOUNT_FILE, "utf-8")) as Account;
  const violations: string[] = [];
  page.on("console", (m) => {
    if (/content security policy|refused to (load|execute|connect)/i.test(m.text())) violations.push(m.text());
  });

  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Username").fill(account.username);
  await page.getByLabel("Passphrase", { exact: true }).fill(account.passphrase ?? "");
  await page.getByRole("button", { name: "Continue" }).click();
  // A throwaway account has never accepted the privacy notice (WP19), so it is shown first.
  await expect(page.getByRole("heading", { name: "Before you start" })).toBeVisible();
  await page.getByRole("button", { name: /i understand/i }).click();
  await expect(page.getByRole("heading", { level: 1, name: /hi, real journey/i })).toBeVisible();
  await expect(page.getByText(/unlocks with four months/i)).toBeVisible();

  await page.getByRole("link", { name: "Import" }).first().click();
  await page.getByLabel("Choose a statement file").setInputFiles(account.csv);
  const add = page.getByRole("button", { name: /^add \d+ transactions?$/i });
  await expect(add).toBeEnabled();
  await add.click();
  await expect(page.getByText(/transactions added/i)).toBeVisible({ timeout: 30_000 });

  await page.getByRole("link", { name: /see your dashboard/i }).click();
  await expect(page.getByRole("img", { name: /score \d+ out of 100/i })).toBeVisible({ timeout: 30_000 });

  await page.goto("/risk");
  await page.getByLabel("What are you buying?").fill("Headphones");
  await page.getByLabel("Number of instalments").fill("3");
  await page.getByLabel(/^price/i).fill("60");
  await page.getByRole("button", { name: "Check this purchase" }).click();
  // the real model decides the band; the journey only needs a result
  await expect(page.getByRole("img", { name: /score \d+ out of 100/i })).toBeVisible({ timeout: 60_000 });

  await page.getByRole("button", { name: "Add this as a plan" }).click();
  await expect(page.getByText("Plan added")).toBeVisible({ timeout: 60_000 });
  await page.getByRole("link", { name: /saved report/i }).click();
  await expect(page).toHaveURL(/\/risk\/[0-9a-f-]{36}/);
  await expect(page.getByRole("heading", { level: 1, name: "Saved risk check" })).toBeVisible();
  await expect(page.getByRole("img", { name: /score \d+ out of 100/i })).toBeVisible();

  await page.goto("/plans");
  await expect(page.getByRole("heading", { name: "Headphones" })).toBeVisible();
  expect(violations).toEqual([]);
});
