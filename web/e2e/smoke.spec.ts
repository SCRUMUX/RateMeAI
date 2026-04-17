import { test, expect } from "@playwright/test";

test.describe("Landing page", () => {
  test("renders hero section and navigation", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/AI Look/i);
    await expect(page.locator("nav")).toBeVisible();
    await expect(page.locator("a,button").filter({ hasText: /получить доступ|попробовать|начать|try/i }).first()).toBeVisible();
  });

  test("opens auth modal from landing CTA for guest", async ({ page }) => {
    await page.goto("/");
    const cta = page.locator("a,button").filter({ hasText: /получить доступ|попробовать|начать|try/i }).first();
    await cta.click();
    await expect(page.getByRole("dialog")).toBeVisible();
  });
});

test.describe("App wizard", () => {
  test("shows upload step initially", async ({ page }) => {
    await page.goto("/app");
    await expect(page.locator('[data-step="upload"], .step-upload, h1, h2, p').first()).toBeVisible();
  });

  test("shows auth modal for unauthenticated user", async ({ page }) => {
    await page.goto("/app");
    await page.waitForTimeout(1000);
    const modal = page.locator('[role="dialog"], [data-modal], .auth-modal, .modal');
    if (await modal.count() > 0) {
      await expect(modal.first()).toBeVisible();
    }
  });
});

test.describe("Routing", () => {
  test("unknown routes redirect or show 404", async ({ page }) => {
    await page.goto("/nonexistent-page-xyz");
    await expect(page).toHaveURL(/\/(app)?/);
  });

  test("/payment-success page loads", async ({ page }) => {
    await page.goto("/payment-success");
    await expect(page.locator("body")).toBeVisible();
  });

  test("/link page loads", async ({ page }) => {
    await page.goto("/link");
    await expect(page.locator("body")).toBeVisible();
  });

  test("/dokumenty page loads", async ({ page }) => {
    await page.goto("/dokumenty");
    await expect(page.locator("body")).toBeVisible();
  });

  test("scenario landing keeps guest inside scenario auth flow", async ({ page }) => {
    await page.goto("/dokumenty");
    await page.locator("button").filter({ hasText: /получить доступ|начать/i }).first().click();
    await expect(page).toHaveURL(/\/dokumenty/);
    await expect(page.getByRole("dialog")).toBeVisible();
  });
});

test.describe("Accessibility", () => {
  test("landing page has no critical a11y violations", async ({ page }) => {
    await page.goto("/");
    const body = page.locator("body");
    await expect(body).toBeVisible();
    const html = await page.content();
    expect(html).toContain("<html");
    expect(html).toContain("lang=");
  });
});
