import { artifactPath, expect, test } from "./fixtures";
import type { HyperframesPlayer } from "@hyperframes/player";
import type { Page } from "@playwright/test";

// Playwright normally hides native scrollbars, which masked this regression.
test.use({ launchOptions: {
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  ignoreDefaultArgs: ["--hide-scrollbars"],
  args: ["--disable-features=OverlayScrollbar,OverlayScrollbars"],
} });

async function identity(page: Page) {
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: {} }));
}

async function expectScrollReleased(page: Page) {
  await expect(page.locator(".login-intro")).toBeHidden({ timeout: 10000 });
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).overflow)).not.toBe("hidden");
  const dimensions = await page.evaluate(() => ({ height: innerHeight, scrollHeight: document.documentElement.scrollHeight, width: innerWidth, clientWidth: document.documentElement.clientWidth }));
  expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.height);
  expect(dimensions.clientWidth).toBeLessThan(dimensions.width);
  await page.mouse.wheel(0, 200);
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(0);
}

test("el primer render ya ocupa todo el viewport mientras JavaScript sigue pendiente", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 600 });
  await identity(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/_next/static/**/*.js", async route => { await gate; await route.continue(); });
  await page.goto("/", { waitUntil: "commit" });
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "pending");
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.documentElement).overflow)).toBe("hidden");
  expect(await page.evaluate(() => document.documentElement.clientWidth)).toBe(1440);
  await page.screenshot({ path: artifactPath("fracxion-intro-viewport/pending-before-hydration.png") });
  release();
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await page.getByRole("button", { name: "Omitir introducción" }).click();
  await expectScrollReleased(page);
});

for (const viewport of [{ width: 1440, height: 600 }, { width: 390, height: 600 }]) {
  test(`sin scrollbar ni franjas durante carga/reproducción; scroll al terminar a ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await identity(page);
    let release!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route("**/hyperframes/fracxion-intro/index.html", async route => { await gate; await route.continue(); });
    await page.goto("/");
    await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "loading");
    expect(await page.evaluate(() => document.documentElement.clientWidth)).toBe(viewport.width);
    await page.mouse.wheel(0, 200);
    expect(await page.evaluate(() => scrollY)).toBe(0);
    await page.screenshot({ path: artifactPath(`fracxion-intro-viewport/loading-${viewport.width}.png`) });
    release();
    await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
    const player = page.locator("hyperframes-player");
    await player.evaluate(element => (element as HyperframesPlayer).pause());
    const bounds = await player.evaluate(element => {
      const iframe = (element as HyperframesPlayer).iframeElement;
      const rect = iframe.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, border: getComputedStyle(iframe).borderWidth, clientWidth: document.documentElement.clientWidth };
    });
    expect(bounds.x).toBeCloseTo(0, 1);
    expect(bounds.y).toBeCloseTo(0, 1);
    expect(bounds.width).toBeCloseTo(viewport.width, 1);
    expect(bounds.height).toBeCloseTo(viewport.height, 1);
    expect(bounds.clientWidth).toBe(viewport.width);
    expect(bounds.border).toBe("0px");
    await page.screenshot({ path: artifactPath(`fracxion-intro-viewport/playing-${viewport.width}.png`) });
    await player.evaluate(element => (element as HyperframesPlayer).play());
    await expectScrollReleased(page);
    await page.screenshot({ path: artifactPath(`fracxion-intro-viewport/login-scroll-${viewport.width}.png`) });
  });
}

test("omisión, error y movimiento reducido liberan el scroll", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 600 });
  await identity(page);
  await page.goto("/");
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await page.getByRole("button", { name: "Omitir introducción" }).click();
  await expectScrollReleased(page);
  await page.route("**/hyperframes/fracxion-intro/index.html", route => route.abort());
  await page.reload();
  await expectScrollReleased(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expectScrollReleased(page);
});

test("sin JavaScript el login no queda bloqueado por el estado pendiente", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1440, height: 600 } });
  const page = await context.newPage();
  try {
    await page.goto("/");
    await expect(page.locator(".login-intro")).toBeHidden();
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).overflow)).not.toBe("hidden");
    await page.mouse.wheel(0, 200);
    await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(0);
  } finally { await context.close(); }
});
