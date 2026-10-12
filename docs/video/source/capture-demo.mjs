import { chromium } from '../../../frontend/node_modules/playwright/index.mjs';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const out = resolve(dirname(fileURLToPath(import.meta.url)), 'demo-captures');
await mkdir(out, { recursive: true });
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-gpu'] });
const errors = [];
const refresh = process.argv.includes('--refresh-results');
const evidence = refresh ? JSON.parse(await readFile(resolve(out, 'capture-evidence.json'), 'utf8')) : { synthetic: true, backend: 'isolated PostgreSQL on 55435', captures: {}, operations: [] };
let activePage;
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  await context.route('**/api/**', async route => {
    const original = new URL(route.request().url());
    const target = new URL(original.pathname + original.search, 'http://127.0.0.1:8012');
    const headers = await route.request().allHeaders();
    delete headers.host;
    const response = await route.fetch({ url: target.href, headers });
    if (response.status() >= 500) errors.push(`HTTP ${response.status()}: ${original.pathname}`);
    await route.fulfill({ response });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  activePage = page;
  page.on('pageerror', error => errors.push(error.message));
  const base = '/dashboard/00000000-0000-4000-8000-000000000001';
  async function visible(locator) { await locator.waitFor({ state: 'visible' }); }
  async function capture(name, markers = {}) {
    await page.evaluate(() => document.activeElement?.blur());
    await page.evaluate(() => document.fonts.ready);
    await page.locator('main:visible').last().getByText(/Cargando información/).last().waitFor({ state: 'hidden' });
    const positions = {};
    for (const [key, locator] of Object.entries(markers)) positions[key] = await locator.boundingBox();
    const text = await page.locator('main:visible').last().innerText();
    if (/no está disponible|error al|no se pudo/i.test(text)) throw new Error(text);
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`Desbordamiento en ${name}`);
    await page.screenshot({ path: resolve(out, `${name}.png`) });
    evidence.captures[name] = { viewport: page.viewportSize(), path: new URL(page.url()).pathname, markers: positions, text };
    console.log(`Captura ${name}`);
  }
  await page.goto('http://127.0.0.1:3010/');
  await page.getByLabel('Correo electrónico', { exact: true }).fill('owner@demo.example');
  await page.getByLabel('Contraseña', { exact: true }).fill('SyntheticVideoPassword2026!');
  await page.getByRole('button', { name: 'Iniciar sesión', exact: true }).click();
  await page.waitForURL(/\/dashboard$/);
  if (refresh) {
    if (!process.env.FRACXION_DEMO_INVOICE_PATH) throw new Error('Se requiere el comprobante sintético existente.');
    await page.goto(`http://127.0.0.1:3010${base}`);
    await visible(page.getByText('Clientes activos', { exact: true }));
    await capture('dashboard-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await visible(page.getByText('Clientes activos', { exact: true }));
    await page.screenshot({ path: resolve(out, 'dashboard-mobile-full.png'), fullPage: true });
    evidence.captures['dashboard-mobile-full'] = { viewport: page.viewportSize(), path: base };
    await page.goto(`http://127.0.0.1:3010${process.env.FRACXION_DEMO_INVOICE_PATH}`);
    await visible(page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }));
    await visible(page.getByRole('cell', { name: 'ARS 400,00', exact: true }));
    await page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }).scrollIntoViewIfNeeded();
    await capture('payment-result-mobile', { balance: page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }) });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(`http://127.0.0.1:3010${process.env.FRACXION_DEMO_INVOICE_PATH}`);
    await visible(page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }));
    await capture('invoice-paid');
  } else {
  await page.goto(`http://127.0.0.1:3010${base}/customers`);
  await visible(page.getByRole('heading', { name: 'Clientes', exact: true }));
  await visible(page.getByText('Estudio Sur', { exact: true }));
  await capture('customers', { customer: page.getByText('Estudio Sur', { exact: true }), newCustomer: page.getByRole('button', { name: 'Nuevo cliente', exact: true }) });
  await page.goto(`http://127.0.0.1:3010${base}/products`);
  await visible(page.getByRole('row').filter({ hasText: 'Soporte mensual' }).getByRole('cell').first());
  await capture('catalog');
  await page.goto(`http://127.0.0.1:3010${base}/invoices/new`);
  await page.getByLabel('Buscar cliente', { exact: true }).fill('Estudio Sur');
  await page.getByLabel('Cliente', { exact: true }).selectOption({ label: 'Estudio Sur' });
  await page.getByLabel('Buscar producto', { exact: true }).fill('Soporte mensual');
  await page.getByLabel('Producto', { exact: true }).selectOption({ label: 'Soporte mensual · ARS 1.000,00' });
  await capture('invoice-builder', { customer: page.getByLabel('Cliente', { exact: true }), product: page.getByLabel('Producto', { exact: true }), save: page.getByRole('button', { name: 'Guardar borrador', exact: true }) });
  if (process.env.FRACXION_DEMO_INVOICE_PATH) {
    await page.goto(`http://127.0.0.1:3010${process.env.FRACXION_DEMO_INVOICE_PATH}`);
  } else {
    await page.getByRole('button', { name: 'Guardar borrador', exact: true }).click();
    await visible(page.getByRole('heading', { name: 'Borrador', exact: true }));
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: 'Emitir factura interna', exact: true }).click();
  }
  await visible(page.getByRole('heading', { name: 'Interna #1', exact: true }));
  const invoicePath = new URL(page.url()).pathname;
  await capture('invoice-issued', { register: page.getByRole('button', { name: 'Registrar pago', exact: true }) });
  evidence.operations.push('Borrador creado y emitido desde UI; total ARS 1.210,00.');
  await page.goto(`http://127.0.0.1:3010${base}`);
  await visible(page.getByRole('heading', { name: 'Demo Fracxion', exact: true }));
  await capture('dashboard-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await visible(page.getByRole('heading', { name: 'Demo Fracxion', exact: true }));
  await visible(page.getByText('Clientes activos', { exact: true }));
  await page.screenshot({ path: resolve(out, 'dashboard-mobile-full.png'), fullPage: true });
  evidence.captures['dashboard-mobile-full'] = { viewport: page.viewportSize(), path: base };
  // Open the actual invoice payment dialog: its selected invoice is already clear.
  await page.goto(`http://127.0.0.1:3010${invoicePath}`);
  await visible(page.getByRole('heading', { name: 'Interna #1', exact: true }));
  await page.getByRole('button', { name: 'Registrar pago', exact: true }).click();
  await page.getByLabel('Importe (ARS) *', { exact: true }).fill('400.00');
  const method = page.getByRole('dialog').getByRole('combobox').first();
  await method.selectOption('bank_transfer');
  await page.getByLabel(/^Referencia externa/).fill('DEMO-001');
  await capture('payment-mobile', { amount: page.getByLabel('Importe (ARS) *', { exact: true }), method });
  await page.getByRole('dialog').getByRole('button', { name: 'Registrar pago', exact: true }).scrollIntoViewIfNeeded();
  await capture('payment-mobile-submit', { submit: page.getByRole('dialog').getByRole('button', { name: 'Registrar pago', exact: true }) });
  await page.getByRole('dialog').getByRole('button', { name: 'Registrar pago', exact: true }).click();
  await page.getByRole('dialog').waitFor({ state: 'detached' });
  await visible(page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }));
  await page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }).scrollIntoViewIfNeeded();
  await capture('payment-result-mobile', { balance: page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }) });
  await page.reload();
  await visible(page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }));
  evidence.operations.push('Pago de ARS 400,00 por transferencia registrado desde UI; saldo ARS 810,00 persistente tras recarga.');
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`http://127.0.0.1:3010${invoicePath}`);
  await visible(page.getByText('Pagado: ARS 400,00 · Saldo: ARS 810,00', { exact: true }));
  await capture('invoice-paid');
  }
  if (errors.length) throw new Error(JSON.stringify(errors));
  evidence.errors = errors;
  await writeFile(resolve(out, 'capture-evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify({ captures: Object.keys(evidence.captures), operations: evidence.operations, errors }));
} catch (error) {
  if (activePage) {
    await activePage.screenshot({ path: resolve(out, 'capture-error.png') });
    console.error(await activePage.locator('body').innerText());
  }
  throw error;
} finally { await browser.close(); }
