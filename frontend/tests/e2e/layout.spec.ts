import { expect, test, type Page } from "@playwright/test";

/** WP7: every screen fits a small phone with no sideways scrolling. Uses the persona-loaded,
 * consented assistant account (read-only visits), on the phone project only. */
const SCREENS = [
  "/",
  "/transactions",
  "/categories",
  "/recurring",
  "/plans",
  "/risk",
  "/budgets",
  "/insights",
  "/import",
  "/account",
  "/model",
  "/security",
];

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("e2e-phone-assistant-llm");
  await page
    .getByLabel("Passphrase", { exact: true })
    .fill("correct horse battery staple");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: /^hi,/i }),
  ).toBeVisible();
}

async function overflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
}

for (const width of [360, 375]) {
  test(`every screen fits a ${width} px phone without sideways scrolling`, async ({
    page,
  }) => {
    test.skip(test.info().project.name !== "phone", "phone widths only");
    await page.setViewportSize({ width, height: 780 });
    for (const path of ["/welcome", "/login"]) {
      await page.goto(path);
      expect(await overflow(page), path).toBeLessThanOrEqual(0);
    }
    await signIn(page);
    for (const path of SCREENS) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(await overflow(page), path).toBeLessThanOrEqual(0);
    }
    await page.goto("/");
    await page.getByRole("button", { name: "Ask PaySense" }).click();
    await expect(
      page.getByRole("dialog", { name: "Ask PaySense" }),
    ).toBeVisible();
    expect(await overflow(page), "assistant panel").toBeLessThanOrEqual(0);
  });
}
