import { expect, test, type Page } from "@playwright/test";

/**
 * The assistant (WP5). The e2e backend runs with E2E_FAKE_LLM=1: the "assistant-llm" testers talk
 * to a scripted model (backend/tests/e2e_server.py), the "assistant-guided" testers have no model.
 * Both start with the frequent_bnpl persona ledger already loaded.
 */
async function signIn(page: Page, journey: string) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(`e2e-${test.info().project.name}-${journey}`);
  await page.getByLabel("Passphrase", { exact: true }).fill("correct horse battery staple");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /hi, e2e tester/i })).toBeVisible();
}

async function openAssistant(page: Page) {
  await page.getByRole("button", { name: "Ask PaySense" }).click();
  const panel = page.getByRole("dialog", { name: "Ask PaySense" });
  await expect(panel).toBeVisible();
  await expect(panel.getByLabel("Your message")).toBeFocused();
  await expect(panel.getByText(/not financial advice or a credit decision/i)).toBeVisible();
  // The opening turn (the alerts, no model call) has arrived.
  await expect(panel.getByText("Looking at your money…")).toBeHidden();
  return panel;
}

test("guided mode: a quick action shows a card, and a budget saves only after Confirm", async ({
  page,
}) => {
  await signIn(page, "assistant-guided");
  const panel = await openAssistant(page);
  await expect(panel.getByText("Guided mode: buttons and forms")).toBeVisible();

  await panel.getByRole("button", { name: "What I owe" }).click();
  await expect(panel.getByRole("heading", { name: /bills and what is due/i })).toBeVisible();

  await panel.getByRole("button", { name: "Set a budget" }).click();
  const form = panel.getByRole("form", { name: "Set a budget" });
  await form.getByLabel("Category").fill("Food");
  await form.getByLabel("Monthly limit (RM)").fill("400");
  await form.getByRole("button", { name: "Propose this budget" }).click();

  const card = panel.getByRole("region", { name: "Save this budget?" });
  await expect(card).toBeVisible();
  await expect(card.getByText("Needs your OK")).toBeVisible();
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(card.getByText("Food budget saved.")).toBeVisible();

  // The saved budget is now read back by a quick action.
  await panel.getByRole("button", { name: "My budgets" }).click();
  await expect(panel.getByRole("progressbar", { name: "Food budget" })).toBeVisible();

  await panel.getByRole("button", { name: "Close" }).click();
  await expect(panel).toBeHidden();
  await expect(page.getByRole("button", { name: "Ask PaySense" })).toBeFocused();
});

test("llm mode: asks if a phone is affordable, sees the risk check, proposes the plan and confirms it", async ({
  page,
}) => {
  test.setTimeout(90_000); // the risk check runs the forecast simulations
  await signIn(page, "assistant-llm");
  const panel = await openAssistant(page);
  await expect(panel.getByText("Assistant on (fake)")).toBeVisible();

  await panel
    .getByRole("button", { name: "Can I afford an RM799 phone on SPayLater over 3 months?" })
    .click();
  await expect(panel.getByText(/here is the risk check for the phone/i)).toBeVisible();
  await expect(panel.getByRole("img", { name: /score \d+ out of 100/i })).toBeVisible();
  await expect(panel.getByText(/what i did \(1 step\)/i).last()).toBeVisible();

  const message = panel.getByLabel("Your message");
  await message.fill("Yes, go ahead.");
  await message.press("Enter");

  const card = panel.getByRole("region", { name: "Add this BNPL plan?" });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Confirm" }).click();
  await expect(card.getByText("Plan added and its risk report saved.")).toBeVisible();

  await card.getByRole("link", { name: /saved report/i }).click();
  await expect(page).toHaveURL(/\/risk\/[0-9a-f-]{36}/);
  await expect(page.getByRole("heading", { level: 1, name: "Saved risk check" })).toBeVisible();
});
