import { artifactPath, expect, test } from "./fixtures";
import type { Page } from "@playwright/test";

const api = "http://127.0.0.1:8001";
const password = "SyntheticE2EPassword2026!";
const root = "/dashboard/00000000-0000-4000-8000-000000000001";

async function openLogin(page: Page) {
  await page.goto("/");
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", /playing|complete/);
  if (await page.locator(".login-experience").getAttribute("data-intro-state") === "playing") {
    await page.getByRole("button", { name: "Omitir introducción" }).click();
  }
}

async function submitLogin(page: Page, role = "owner") {
  await openLogin(page);
  await page.getByLabel("Correo electrónico", { exact: true }).fill(`${role}@e2e.example`);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
}

async function waitForDashboard(page: Page) {
  await expect(page.getByRole("link", { name: "Abrir el espacio de trabajo de Empresa E2E", exact: true })).toBeVisible({ timeout: 8000 });
}

test("bienvenida con identidad real, sin credenciales, y despedida segura desde el selector", async ({ page }) => {
  await submitLogin(page);
  const welcome = page.locator('[data-session-transition="welcome"]');
  await expect(welcome).toBeVisible();
  await expect(welcome.getByRole("heading")).toContainText("Bienvenido/a,");
  await expect(welcome.getByRole("heading")).toContainText("Prueba");
  expect(await page.locator("#email").inputValue()).toBe("");
  expect(await page.locator("#password").inputValue()).toBe("");
  await page.keyboard.press("Tab");
  await expect(welcome.getByRole("button", { name: "Continuar" })).toBeFocused();
  await page.waitForFunction(() => {
    const heading = document.querySelector(".session-transition-heading");
    return heading && Number(getComputedStyle(heading).opacity) >= .99;
  });
  await page.screenshot({ path: artifactPath("fracxion-auth-transitions/welcome-desktop.png") });
  await waitForDashboard(page);
  await page.reload();
  await waitForDashboard(page);
  await expect(page.locator(".session-transition, .login-intro")).toHaveCount(0);
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  const farewell = page.locator('[data-session-transition="farewell"]');
  await expect(farewell).toBeVisible();
  await expect(farewell.getByRole("heading")).toContainText("Prueba");
  await expect(page.locator(".session-content, .workspace-shell")).toHaveCount(0);
  expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(401);
  await expect(page).toHaveURL("http://127.0.0.1:3010/");
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await expect(page.locator("hyperframes-player")).toHaveCount(1);
  await expect(page.locator(".login-intro")).toBeHidden({ timeout: 10000 });
  await page.reload();
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
});

test("el usuario sin nombre recibe una bienvenida con su empresa autorizada", async ({ page }) => {
  await submitLogin(page, "nameless");
  const welcome = page.locator('[data-session-transition="welcome"]');
  await expect(welcome.getByRole("heading")).toContainText("Empresa E2E");
  await welcome.getByRole("button", { name: "Continuar" }).click();
  await waitForDashboard(page);
});

test("despedida de empresa en móvil retira el contenido privado antes de volver al login", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await submitLogin(page);
  await waitForDashboard(page);
  await page.goto(`${root}/customers`);
  await expect(page.getByRole("heading", { name: "Clientes", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  const farewell = page.locator('[data-session-transition="farewell"]');
  await expect(farewell.getByRole("heading")).toContainText("Empresa E2E");
  await expect(page.locator(".business-shell, .data-table, .session-content")).toHaveCount(0);
  expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(401);
  await page.waitForFunction(() => {
    const heading = document.querySelector(".session-transition-heading");
    return heading && Number(getComputedStyle(heading).opacity) >= .99;
  });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: artifactPath("fracxion-auth-transitions/farewell-mobile.png") });
  await expect(page).toHaveURL("http://127.0.0.1:3010/");
  await expect(page.locator(".login-experience")).toHaveAttribute("data-intro-state", "playing");
  await expect(page.locator(".login-intro")).toBeHidden({ timeout: 10000 });
});

test("la F gira durante una carga lenta y el dashboard solo se revela con sus datos listos", async ({ page }) => {
  await openLogin(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/auth/tenants/", async route => {
    await gate;
    await route.continue();
  });
  await page.getByLabel("Correo electrónico", { exact: true }).fill("owner@e2e.example");
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  const welcome = page.locator('[data-session-transition="welcome"]');
  await expect(welcome).toHaveAttribute("data-phase", "loading", { timeout: 8000 });
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.locator(".session-content")).toHaveAttribute("inert", "");
  await expect(welcome.getByRole("status")).toContainText("Cargando tu espacio de trabajo");
  const before = await welcome.locator(".session-transition-spin").evaluate(el => getComputedStyle(el).transform);
  await expect.poll(async () => welcome.locator(".session-transition-spin").evaluate(el => getComputedStyle(el).transform)).not.toBe(before);
  expect(await welcome.evaluate(el => getComputedStyle(el).opacity)).toBe("1");
  await page.screenshot({ path: artifactPath("fracxion-smooth-session/loading-desktop.png") });
  release();
  await expect(welcome).toHaveAttribute("data-phase", "revealing");
  await expect.poll(async () => welcome.evaluate(el => Number(getComputedStyle(el).opacity))).toBeLessThan(1);
  await expect(welcome).toHaveCount(0);
  await expect(page.locator(".session-content")).not.toHaveAttribute("inert", "");
  await waitForDashboard(page);
});

test("un error de carga del destino se revela con su opción de reintentar", async ({ page }) => {
  await openLogin(page);
  await page.route("**/api/auth/tenants/", route => route.fulfill({ status: 403, json: { detail: "Carga rechazada de prueba." } }), { times: 1 });
  await page.getByLabel("Correo electrónico", { exact: true }).fill("owner@e2e.example");
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await expect(page.locator(".session-transition")).toHaveCount(0, { timeout: 10000 });
  await expect(page.locator(".workspace-content").getByRole("alert")).toContainText("Carga rechazada de prueba");
  await page.getByRole("button", { name: "Reintentar", exact: true }).click();
  await waitForDashboard(page);
});

test("credenciales inválidas no muestran bienvenida y un logout rechazado no muestra despedida", async ({ page }) => {
  await openLogin(page);
  await page.getByLabel("Correo electrónico", { exact: true }).fill("owner@e2e.example");
  await page.getByLabel("Contraseña", { exact: true }).fill("WrongSyntheticPassword!");
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await expect(page.locator(".login-form").getByRole("alert")).toContainText("no son correctos");
  await expect(page.locator(".session-transition")).toHaveCount(0);
  await page.getByLabel("Contraseña", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Iniciar sesión", exact: true }).click();
  await waitForDashboard(page);
  await page.route("**/api/auth/logout/", route => route.fulfill({ status: 403, json: { detail: "Solicitud rechazada de prueba." } }), { times: 1 });
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  await expect(page.locator(".workspace-content").getByRole("alert")).toContainText("No se pudo cerrar la sesión");
  await expect(page.locator(".session-transition")).toHaveCount(0);
  expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(200);
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  await expect(page.locator('[data-session-transition="farewell"]')).toBeVisible();
  await expect(page).toHaveURL("http://127.0.0.1:3010/");
});

test("movimiento reducido conserva login y logout reales sin esperas de animación", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await submitLogin(page);
  await waitForDashboard(page);
  await expect(page.locator(".session-transition")).toHaveCount(0);
  await page.getByRole("button", { name: "Cerrar sesión", exact: true }).click();
  await expect(page).toHaveURL("http://127.0.0.1:3010/");
  await expect(page.locator(".login-intro")).toBeHidden();
  expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(401);
});
