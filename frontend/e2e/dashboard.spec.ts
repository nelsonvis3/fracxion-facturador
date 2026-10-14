import type { Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { expect, test } from "./fixtures";

const tenant = "00000000-0000-4000-8000-000000000001";
const base = `/dashboard/${tenant}`;
const api = "http://127.0.0.1:8001";

async function login(page: Page, role = "owner") {
  await page.goto("/");
  await expect(page.locator(".login-intro")).toBeHidden({ timeout: 10000 });
  await page.getByLabel("Correo electrónico", { exact: true }).fill(`${role}@e2e.example`);
  await page.getByLabel("Contraseña", { exact: true }).fill("SyntheticE2EPassword2026!");
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true })).toBeVisible();
}

async function checkReadability(page: Page) {
  expect(await page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth))).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) + 1);
  // Comprueba el contraste del texto visible, sin fijar los colores de la implementación.
  const failures = await page.locator("main:visible").evaluate(main => {
    function luminance(color: string) {
      const channels = color.match(/[\d.]+/g)!.slice(0, 3).map(Number).map(value => {
        const normalized = value / 255;
        return normalized <= .04045 ? normalized / 12.92 : ((normalized + .055) / 1.055) ** 2.4;
      });
      return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
    }
    const errors: string[] = [];
    const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
    let node: Node | null;
    while ((node = walker.nextNode())) {
      const element = node.parentElement;
      if (!element || !node.textContent?.trim() || !element.getClientRects().length) continue;
      const style = getComputedStyle(element);
      if (style.visibility !== "visible") continue;
      let background = element;
      while (getComputedStyle(background).backgroundColor === "rgba(0, 0, 0, 0)" && background.parentElement) background = background.parentElement;
      const foregroundLuminance = luminance(style.color);
      const backgroundLuminance = luminance(getComputedStyle(background).backgroundColor);
      const contrast = (Math.max(foregroundLuminance, backgroundLuminance) + .05) / (Math.min(foregroundLuminance, backgroundLuminance) + .05);
      const largeText = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && Number(style.fontWeight) >= 700);
      if (contrast < (largeText ? 3 : 4.5)) errors.push(`${node.textContent.trim()}: ${contrast.toFixed(2)}`);
    }
    return errors;
  });
  expect(failures, "Texto legible sobre las superficies del dashboard").toEqual([]);
}

test("dashboard legible en escritorio, tablet y móvil; navegación y contadores reales", async ({ page }) => {
  test.setTimeout(60000);
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await login(page);
  mkdirSync("../docs/screenshots", { recursive: true });
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 768, height: 1024 }, { width: 390, height: 844 }, { width: 320, height: 800 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/dashboard");
    const company = page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true });
    await expect(company).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mis empresas", exact: true })).toBeVisible();
    await checkReadability(page);
    if (viewport.width === 1440) {
      const sidebar = await page.locator(".workspace-sidebar").boundingBox();
      const content = await page.locator("main:visible").boundingBox();
      expect(content!.x).toBeGreaterThanOrEqual(sidebar!.x + sidebar!.width);
    }
    if (viewport.width === 1440 || viewport.width === 390) await page.screenshot({ path: `../docs/screenshots/dashboard-${viewport.width === 1440 ? "desktop" : "mobile"}.png`, fullPage: true });
    await company.focus();
    await expect(company).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(base);
    await expect(page.getByRole("region", { name: "Resumen de registros" })).toBeVisible();
    const counts = await Promise.all(["customers/?is_active=true", "products/?is_active=true", "invoices/?status=draft", "invoices/?status=issued"].map(async path => {
      const response = await page.request.get(`${api}/api/tenants/${tenant}/${path}`);
      expect(response.status()).toBe(200);
      return String((await response.json()).count);
    }));
    await expect(page.locator(".overview-metric strong")).toHaveText(counts);
    await checkReadability(page);
    if (viewport.width === 1440 || viewport.width === 390) await page.screenshot({ path: `../docs/screenshots/company-dashboard-${viewport.width === 1440 ? "desktop" : "mobile"}.png`, fullPage: true });
    await page.locator(".workspace-modules").getByRole("link", { name: /Clientes/ }).click();
    await expect(page).toHaveURL(`${base}/customers`);
    await expect(page.getByRole("heading", { name: "Clientes", exact: true })).toBeVisible();
  }
  await page.emulateMedia({ colorScheme: "light", reducedMotion: "no-preference" });
  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true })).toBeVisible();
  await checkReadability(page);
});

test("selector muestra carga, error con reintento y estado sin empresas", async ({ page }) => {
  await login(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/auth/tenants/", async route => {
    await pending;
    await route.fulfill({ status: 403, json: { detail: "No se pudieron cargar las empresas de prueba." } });
  }, { times: 1 });
  await page.reload();
  await expect(page.getByRole("status")).toContainText("Cargando empresas");
  release();
  await expect(page.locator("main:visible").getByRole("alert")).toContainText("No se pudieron cargar las empresas de prueba");
  await page.getByRole("button", { name: "Reintentar", exact: true }).click();
  await expect(page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true })).toBeVisible();
  await page.route("**/api/auth/tenants/", route => route.fulfill({ status: 200, json: { results: [] } }), { times: 1 });
  await page.reload();
  await expect(page.getByRole("heading", { name: "No hay empresas asociadas", exact: true })).toBeVisible();
  await expect(page.locator(".workspace-count")).toHaveText("0 empresas");
});

test("resumen viewer conserva permisos al mostrar accesos y acciones", async ({ page }) => {
  await login(page, "viewer");
  await page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true }).click();
  await expect(page.getByRole("region", { name: "Resumen de registros" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Nuevo borrador", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Auditoría/ })).toHaveCount(0);
  await page.getByRole("link", { name: "Ver facturas", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Facturas internas", exact: true })).toBeVisible();
});
