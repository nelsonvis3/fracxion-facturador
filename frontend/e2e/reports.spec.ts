import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { artifactPath, expect, test } from "./fixtures";
import { checkAccessibility } from "./accessibility";
import { api, mutate, register } from "./support";

async function runWorker(job: string) {
  const backend = resolve(process.cwd(), "../backend");
  const python = process.env.E2E_PYTHON ?? resolve(backend, ".venv/bin/python");
  const child = spawn(python, ["manage.py", "run_jobs", "--once", "--job", job, "--settings=config.e2e_settings"], { cwd: backend, env: { ...process.env, DJANGO_ENV: "development", DJANGO_SETTINGS_MODULE: "config.e2e_settings" }, stdio: ["ignore", "pipe", "pipe"] });
  let output = ""; child.stdout.on("data", data => { output += data; }); child.stderr.on("data", data => { output += data; });
  const exit = await new Promise((done, reject) => { child.once("error", reject); child.once("exit", done); });
  expect(exit, output).toBe(0); expect(output).toContain("succeeded");
}

test("informes CSV, Excel y PDF reales; worker separado y avisos privados", async ({ page }) => {
  test.setTimeout(90000);
  const tenant = await register(page); const base = `/api/tenants/${tenant.id}`;
  const customer = await mutate(page.request, `${base}/customers/`, { name: "Cliente de informes" }); expect(customer.status()).toBe(201);
  const product = await mutate(page.request, `${base}/products/`, { name: "Servicio de exportación", unit_price: "100.00", tax_rate: "0", currency: "ARS", product_type: "service", unit: "unit" }); expect(product.status()).toBe(201);
  const invoice = await mutate(page.request, `${base}/invoices/`, { customer: (await customer.json()).id, currency: "ARS", lines: [{ product: (await product.json()).id, quantity: "1" }] }); expect(invoice.status()).toBe(201);
  expect((await mutate(page.request, `${base}/invoices/${(await invoice.json()).id}/issue/`, {})).status()).toBe(200);
  await page.goto(`/dashboard/${tenant.id}/reports`);
  await expect(page.getByRole("heading", { name: "Informes y exportaciones", exact: true })).toBeVisible();
  const [csv] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Descargar ahora", exact: true }).click()]);
  await csv.saveAs(artifactPath("reports-sales.csv"));
  expect(await readFile(artifactPath("reports-sales.csv"), "utf8")).toContain("100.00");
  await page.getByRole("combobox", { name: "Formato", exact: true }).selectOption("pdf");
  const [created] = await Promise.all([page.waitForResponse(response => response.url().endsWith("/reports/jobs/") && response.request().method() === "POST"), page.getByRole("button", { name: "Generar informe", exact: true }).click()]);
  expect(created.status()).toBe(202); const job = await created.json();
  await expect(page.getByRole("cell", { name: /^Pendiente/ })).toBeVisible();
  await runWorker(job.id);
  await page.getByRole("button", { name: "Actualizar historial" }).click();
  await expect(page.getByText("Completado", { exact: true })).toBeVisible();
  const [pdf] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Descargar", exact: true }).click()]);
  await pdf.saveAs(artifactPath("reports-sales.pdf"));
  expect((await readFile(artifactPath("reports-sales.pdf"))).subarray(0, 5).toString()).toBe("%PDF-");
  await page.getByRole("combobox", { name: "Formato", exact: true }).selectOption("xlsx");
  const [xlsx] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Descargar ahora", exact: true }).click()]);
  await xlsx.saveAs(artifactPath("reports-sales.xlsx"));
  expect((await readFile(artifactPath("reports-sales.xlsx"))).subarray(0, 2).toString()).toBe("PK");
  await checkAccessibility(page); await page.screenshot({ path: artifactPath("reports-desktop.png"), fullPage: true });
  await page.goto(`/dashboard/${tenant.id}/notifications`);
  await expect(page.getByRole("heading", { name: /^Informe disponible/ })).toBeVisible();
  await page.getByRole("button", { name: "Marcar como leída" }).click();
  await expect(page.getByText("Nueva", { exact: true })).toHaveCount(0);
  await page.getByLabel("Solo no leídas").check();
  await expect(page.getByText("No hay notificaciones para este filtro.")).toBeVisible();
  expect((await page.request.get(`${api}${base}/reports/jobs/`)).status()).toBe(200);
});

test("configuración de automatizaciones persiste y respeta movimiento reducido y móvil", async ({ page }) => {
  const tenant = await register(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/dashboard/${tenant.id}/automation`);
  await page.getByLabel("Nombre", { exact: true }).fill("Resumen semanal");
  await page.getByLabel("Frecuencia", { exact: true }).selectOption("weekly");
  await page.getByRole("button", { name: "Crear automatización", exact: true }).click();
  const table = page.getByRole("region", { name: "Reglas de automatización" });
  await expect(table.getByRole("cell", { name: /^Resumen semanal/ })).toBeVisible();
  await expect(table.getByText("Desactivada", { exact: true })).toBeVisible();
  await table.getByRole("button", { name: "Habilitar", exact: true }).click();
  await expect(table.getByText("Activa", { exact: true })).toBeVisible();
  await page.reload(); await expect(table.getByText("Activa", { exact: true })).toBeVisible();
  await checkAccessibility(page);
  await page.screenshot({ path: artifactPath("automation-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of ["automation", "reports", "notifications"]) {
    await page.goto(`/dashboard/${tenant.id}/${route}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible(); await checkAccessibility(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: artifactPath(`${route}-390.png`), fullPage: true });
  }
});
