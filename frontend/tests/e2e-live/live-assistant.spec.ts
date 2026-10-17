import fs from "node:fs";
import path from "node:path";

import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * The demo story in the browser with the live model and the served risk model. A live model
 * varies, so this journey asserts what the app guarantees (the risk card comes from the tool, a
 * change waits for Confirm) and records the rest as evidence, including a turn that does not
 * propose.
 */
const OUT = path.resolve(__dirname, "../../../evidence/live-browser");
const log: { step: string; reply: string }[] = [];

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: false });
}

async function ask(panel: Locator, text: string): Promise<string> {
  const replies = panel.getByRole("log").locator("[data-reply]");
  const before = await replies.count();
  const message = panel.getByLabel("Your message");
  await message.fill(text);
  await message.press("Enter");
  // one more reply from the assistant (a provider can take tens of seconds on the free tier)
  await expect.poll(() => replies.count(), { timeout: 150_000 }).toBeGreaterThan(before);
  const reply = await replies.last().innerText();
  log.push({ step: text, reply });
  return reply;
}

test.afterAll(() => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, "replies.json"), JSON.stringify(log, null, 1) + "\n");
});

test("the demo story with the live model", async ({ page }) => {
  test.setTimeout(600_000);
  fs.mkdirSync(OUT, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/login");
  await page.getByLabel("Username").fill("e2e-desktop-assistant-llm");
  await page.getByLabel("Passphrase", { exact: true }).fill("correct horse battery staple");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /hi, e2e tester/i })).toBeVisible();
  await shot(page, "01-dashboard");

  await page.getByRole("button", { name: "Ask PaySense" }).click();
  const panel = page.getByRole("dialog", { name: "Ask PaySense" });
  await expect(panel.getByText("Looking at your money…")).toBeHidden({ timeout: 60_000 });
  const status = await panel.locator("h2 + p").innerText();
  log.push({ step: "status line", reply: status });
  await shot(page, "02-opening");

  await ask(panel, "Can I afford an RM799 phone on SPayLater over 3 months?");
  await expect(panel.getByRole("img", { name: /score \d+ out of 100/i }).last()).toBeVisible();
  await shot(page, "03-afford");

  await ask(panel, "What's the safest way to buy it?");
  await shot(page, "04-safest");

  await ask(panel, "Go ahead with that.");
  let card = panel.getByRole("region", { name: "Add this BNPL plan?" });
  if (!(await card.count())) {
    await ask(
      panel,
      "Please add the RM799 SPayLater phone plan over 3 months so I can confirm it.",
    );
    card = panel.getByRole("region", { name: "Add this BNPL plan?" });
  }
  await shot(page, "05-proposal");
  if (await card.count()) {
    await expect(card.last().getByText("Needs your OK")).toBeVisible();
    await card.last().getByRole("button", { name: "Confirm" }).click();
    await expect(card.last().getByText("Plan added and its risk report saved.")).toBeVisible({
      timeout: 60_000,
    });
    log.push({ step: "Confirm", reply: "Plan added and its risk report saved." });
    await shot(page, "06-confirmed");
  } else {
    log.push({ step: "Confirm", reply: "no plan proposal in two turns: nothing to confirm" });
  }

  await ask(panel, "What do I owe this month?");
  await shot(page, "07-bills");
});
