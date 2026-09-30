import { expect, test } from "@playwright/test";

/**
 * The UI follows the browser's locale (PLAN.md, 2026-09-15).
 *
 * `tests/i18n.test.ts` already holds the catalogues to each other, and `tsc` fails a missing
 * key. What neither can check is the part that actually breaks: whether a real browser
 * announcing `pt-PT` ends up reading Portuguese. That runs through `navigator.languages`, an
 * effect and a context, and it is exactly the class of thing the type checker cannot see —
 * the same reason `await params` needs a browser to catch.
 */
const API = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

async function firstActivity(): Promise<string | null> {
  try {
    const response = await fetch(`${API}/activities`);
    if (!response.ok) return null;
    const rows = (await response.json()) as { activity_id: string }[];
    return rows[0]?.activity_id ?? null;
  } catch {
    return null;
  }
}

test.describe("a Portuguese browser", () => {
  test.use({ locale: "pt-PT" });

  test("reads the session screen in Portuguese", async ({ page }) => {
    test.setTimeout(180_000);
    const activityId = await firstActivity();
    test.skip(activityId === null, "no ingested session — start the API and post an activity");

    await page.goto(`/session/${activityId}`, { waitUntil: "networkidle" });
    await expect(page.locator(".hero-value")).toBeVisible({ timeout: 90_000 });

    await expect(page.locator(".hero-label")).toHaveText("Ondas");
    await expect(page.locator(".method-eyebrow")).toHaveText("Como estes números são feitos");
    await expect(page.locator(".tab").first()).toHaveText("Sessões");
    // Resolution must reach `<html lang>` too, or a screen reader picks the wrong voice.
    await expect(page.locator("html")).toHaveAttribute("lang", "pt-PT");

    await page.screenshot({ path: "verification/session-pt-pt.png", fullPage: true });
  });
});

test.describe("an English browser", () => {
  test.use({ locale: "en-GB" });

  test("reads the same screen in English", async ({ page }) => {
    test.setTimeout(180_000);
    const activityId = await firstActivity();
    test.skip(activityId === null, "no ingested session — start the API and post an activity");

    await page.goto(`/session/${activityId}`, { waitUntil: "networkidle" });
    await expect(page.locator(".hero-value")).toBeVisible({ timeout: 90_000 });

    // en-GB has no catalogue of its own: a rough match in the right language beats an
    // exact match in the wrong one.
    await expect(page.locator(".hero-label")).toHaveText("Waves");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
  });
});
