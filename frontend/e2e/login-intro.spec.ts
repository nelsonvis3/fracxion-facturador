import type { HyperframesPlayer } from "@hyperframes/player";
import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

async function openIntro(page: Page) {
  // Only the unauthenticated identity response is controlled here. The animation,
  // its local assets and the existing form run in the real production frontend.
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: { detail: "Autenticación requerida." } }));
  await page.goto("/");
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await page.locator("hyperframes-player").evaluate(element => (element as HyperframesPlayer).pause());
}

async function inspectFrame(page: Page, time: number) {
  return page.locator("hyperframes-player").evaluate((element, seconds) => {
    const player = element as HyperframesPlayer;
    player.seek(seconds);
    const doc = player.iframeElement.contentDocument!;
    const mark = doc.querySelector<HTMLElement>("#mark")!;
    const markRect = mark.getBoundingClientRect();
    const letters = [...doc.querySelectorAll<HTMLElement>("#word span")];
    const word = doc.querySelector<HTMLElement>("#word")!;
    const wordRect = word.getBoundingClientRect();
    const mask = doc.defaultView!.getComputedStyle(doc.querySelector("#word-window")!).clipPath;
    const rightInset = parseFloat(mask.replace(/^inset\(|\)$/g, "").trim().split(/\s+/)[1] || "0");
    return {
      mark: { x: markRect.x, y: markRect.y, width: markRect.width, height: markRect.height },
      letters: letters.map(letter => Number(doc.defaultView!.getComputedStyle(letter).opacity)),
      word: { text: word.textContent, left: wordRect.left, right: wordRect.right },
      revealed: 1 - rightInset / 100,
      offsets: letters.map(letter => (letter.getBoundingClientRect().left - wordRect.left) / wordRect.width),
      markOpacity: Number(doc.defaultView!.getComputedStyle(mark).opacity),
      backdropOpacity: Number(doc.defaultView!.getComputedStyle(doc.querySelector("#backdrop")!).opacity),
    };
  }, time);
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
  test(`F, Fracxion, retracción y llegada al logo real a ${viewport.width}px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const externalAssets: string[] = [];
    page.on("request", request => {
      if (!["127.0.0.1", "localhost"].includes(new URL(request.url()).hostname)) externalAssets.push(request.url());
    });
    await openIntro(page);
    expect(await page.locator(".login-content").evaluate(element => (element as HTMLElement).inert)).toBe(true);

    const first = await inspectFrame(page, .6);
    expect(first.mark.x + first.mark.width / 2).toBeCloseTo(viewport.width / 2, 0);
    expect(first.revealed).toBe(0);
    expect(first.markOpacity).toBe(1);

    const word = await inspectFrame(page, 1.8);
    expect(word.word.text).toBe("racxion");
    expect(word.letters.every(opacity => opacity === 1)).toBe(true);
    expect(word.revealed).toBe(1);
    expect(word.mark.x).toBeGreaterThan(0);
    expect(word.word.right).toBeLessThan(viewport.width);
    await page.screenshot({ path: `/tmp/fracxion-enterprise-audit/intro-${viewport.width}-word.png` });

    // Inspect intermediate frames: each glyph preserves its place in the word,
    // so a passing final frame cannot hide overlap during emergence/retraction.
    for (const time of [.65, .82, 1.05, 1.3, 2.2, 2.45, 2.7]) {
      const sample = await inspectFrame(page, time);
      sample.offsets.forEach((offset, index) => expect(offset).toBeCloseTo(word.offsets[index], 4));
    }
    await inspectFrame(page, 1.05);
    await page.screenshot({ path: `/tmp/fracxion-auth-transitions/clean-${viewport.width}-emergence.png` });

    const closed = await inspectFrame(page, 2.8);
    expect(closed.revealed).toBe(0);
    expect(closed.mark.x + closed.mark.width / 2).toBeCloseTo(viewport.width / 2, 0);

    const arrived = await inspectFrame(page, 4.25);
    const destination = await page.locator("[data-login-brand]:visible").boundingBox();
    expect(arrived.mark.x).toBeCloseTo(destination!.x, 0);
    expect(arrived.mark.y).toBeCloseTo(destination!.y, 0);
    expect(arrived.mark.width).toBeCloseTo(destination!.width, 0);
    expect(arrived.backdropOpacity).toBeLessThan(.15);
    await page.screenshot({ path: `/tmp/fracxion-enterprise-audit/intro-${viewport.width}-arrival.png` });

    await page.locator("hyperframes-player").evaluate(element => (element as HyperframesPlayer).play());
    await expect(page.locator(".login-intro")).toBeHidden();
    expect(await page.locator(".login-content").evaluate(element => (element as HTMLElement).inert)).toBe(false);
    await expect(page.getByRole("heading", { name: "Qué bueno verte de nuevo." })).toBeVisible();
    await page.getByLabel("Correo electrónico", { exact: true }).fill("person@example.test");
    await page.getByLabel("Contraseña", { exact: true }).fill("ExamplePassword!");
    await expect(page.getByRole("button", { name: "Iniciar sesión", exact: true })).toBeEnabled();
    expect(externalAssets).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/fracxion-enterprise-audit/intro-${viewport.width}-login.png`, fullPage: true });

    await page.reload();
    await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
    await expect(page.locator("hyperframes-player")).toHaveCount(1);
    await page.getByRole("button", { name: "Omitir introducción" }).click();
  });
}

test("se puede omitir con teclado y el foco pasa al correo", async ({ page }) => {
  await openIntro(page);
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Omitir introducción" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".login-intro")).toBeHidden();
  await expect(page.getByLabel("Correo electrónico", { exact: true })).toBeFocused();
  await page.getByRole("link", { name: "¿Olvidaste tu contraseña?" }).click();
  await expect(page).toHaveURL(/\/forgot-password$/);
});

test("movimiento reducido permite entrar directamente", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: {} }));
  await page.goto("/");
  await expect(page.locator(".login-intro")).toBeHidden();
  await expect(page.locator("hyperframes-player")).toHaveCount(0);
  await page.getByLabel("Correo electrónico", { exact: true }).fill("person@example.test");
  await page.getByRole("link", { name: "Crear cuenta", exact: true }).click();
  await expect(page).toHaveURL(/\/register$/);
});

test("un fallo de la composición no bloquea el login", async ({ page }) => {
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: {} }));
  await page.route("**/hyperframes/fracxion-intro/index.html", route => route.abort());
  await page.goto("/");
  await expect(page.locator(".login-intro")).toBeHidden();
  await page.getByLabel("Correo electrónico", { exact: true }).fill("person@example.test");
});

test("Escape y un cambio de viewport dejan disponible el formulario", async ({ page }) => {
  await openIntro(page);
  await page.keyboard.press("Escape");
  await expect(page.locator(".login-intro")).toBeHidden();
  await page.reload();
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".login-intro")).toBeHidden();
  await page.getByLabel("Correo electrónico", { exact: true }).fill("person@example.test");
});

test("la introducción se reproduce y termina automáticamente a velocidad normal", async ({ page }) => {
  await page.route("**/api/auth/me/", route => route.fulfill({ status: 401, json: {} }));
  await page.goto("/");
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await expect(page.locator(".login-intro")).toBeHidden({ timeout: 7000 });
  await expect(page.locator("hyperframes-player")).toHaveCount(0);
  await page.getByLabel("Correo electrónico", { exact: true }).fill("person@example.test");
});

test("el almacenamiento restringido no impide reproducir ni omitir", async ({ page }) => {
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new DOMException("Blocked", "SecurityError"); };
    Storage.prototype.setItem = () => { throw new DOMException("Blocked", "SecurityError"); };
  });
  await openIntro(page);
  await page.getByRole("button", { name: "Omitir introducción" }).click();
  await expect(page.locator(".login-intro")).toBeHidden();
  await page.getByLabel("Correo electrónico", { exact: true }).fill("person@example.test");
});
