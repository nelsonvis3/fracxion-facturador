import { artifactPath, expect, test } from "./fixtures";
import { checkAccessibility } from "./accessibility";
import { api, mutate, register } from "./support";

test("compras reales: borrador, confirmación, recepciones, reversión atómica, gasto asociado y cierre", async ({page})=>{
  test.setTimeout(150000);
  const tenant=await register(page);const base=`/api/tenants/${tenant.id}`;
  const supplierResponse=await mutate(page.request,`${base}/suppliers/`,{name:"Proveedor industrial",country_code:"AR"});expect(supplierResponse.status()).toBe(201);
  const productResponse=await mutate(page.request,`${base}/products/`,{name:"Insumo de compra",product_type:"product",unit:"unit",unit_price:"25.00",tax_rate:"21.00",currency:"ARS"});expect(productResponse.status()).toBe(201);const product=await productResponse.json();
  expect((await mutate(page.request,`${base}/inventory/items/${product.id}/`,{tracking:true,minimum:"0.000"},"PATCH")).status()).toBe(200);
  await page.goto(`/dashboard/${tenant.id}/purchases`);await page.getByRole("button",{name:"Nuevo pedido de compra",exact:true}).click();
  let dialog=page.getByRole("dialog");await dialog.getByRole("combobox",{name:"Proveedor del pedido",exact:true}).selectOption({label:"Proveedor industrial"});await dialog.getByLabel("Referencia del pedido",{exact:true}).fill("OC-E2E-01");
  await dialog.getByRole("combobox",{name:"Producto o servicio 1",exact:true}).selectOption({label:"Insumo de compra"});await dialog.getByLabel("Cantidad 1",{exact:true}).fill("5.000");await dialog.getByLabel("Costo unitario 1",{exact:true}).fill("10.0000");await dialog.getByLabel("Impuesto de línea 1 (%)",{exact:true}).fill("21.00");
  await checkAccessibility(page);await dialog.getByRole("button",{name:"Guardar borrador de compra"}).click();await expect(dialog).toHaveCount(0);
  await page.getByRole("link",{name:"OC-E2E-01",exact:true}).click();await page.waitForURL(/purchases\/[0-9a-f-]+$/);const id=page.url().split("/").at(-1)!;
  page.once("dialog",dialog=>dialog.accept());await page.getByRole("button",{name:"Confirmar pedido",exact:true}).click();await expect(page.getByRole("button",{name:"Registrar recepción",exact:true})).toBeVisible();
  const lineTable=page.getByRole("region",{name:"Líneas y cantidades del pedido",exact:true});await expect(lineTable.getByRole("cell",{name:"ARS 60,50",exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Registrar recepción",exact:true}).click();dialog=page.getByRole("dialog");await dialog.getByLabel("Referencia de entrega",{exact:true}).fill("REM-E2E-01");await dialog.getByLabel("Recibir Insumo de compra").fill("2.000");await dialog.getByRole("button",{name:"Confirmar recepción",exact:true}).click();await expect(dialog).toHaveCount(0);
  let lines=await (await page.request.get(`${api}${base}/purchases/${id}/lines/`)).json();expect(lines[0].received_quantity).toBe("2.000");expect(lines[0].remaining_quantity).toBe("3.000");
  const receipts=await (await page.request.get(`${api}${base}/purchases/${id}/receipts/`)).json();const movement=receipts.results[0].lines[0].movement;
  expect((await mutate(page.request,`${base}/inventory/movements/${movement}/reverse/`,{reason:"Evitar recepción"})).status()).toBe(400);
  const expenseList=await (await page.request.get(`${api}${base}/expenses/`)).json();expect(expenseList.count).toBe(0);
  expect((await mutate(page.request,`${base}/inventory/movements/`,{product:product.id,kind:"out",quantity:"1.000",reason:"Uso antes de devolución"})).status()).toBe(201);
  await page.getByRole("button",{name:"Revertir recepción",exact:true}).click();dialog=page.getByRole("dialog");await dialog.getByLabel("Motivo",{exact:true}).fill("Entrega errónea");await dialog.getByRole("button",{name:"Confirmar",exact:true}).click();await expect(dialog.getByRole("alert")).toContainText("negativo");
  await dialog.getByRole("button",{name:"Cancelar",exact:true}).click();
  expect((await mutate(page.request,`${base}/inventory/movements/`,{product:product.id,kind:"in",quantity:"1.000",reason:"Devolución del consumo"})).status()).toBe(201);
  await page.getByRole("button",{name:"Revertir recepción",exact:true}).click();dialog=page.getByRole("dialog");await dialog.getByLabel("Motivo",{exact:true}).fill("Entrega errónea");await dialog.getByRole("button",{name:"Confirmar",exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("cell",{name:"Revertida",exact:false})).toBeVisible();
  lines=await (await page.request.get(`${api}${base}/purchases/${id}/lines/`)).json();expect(lines[0].received_quantity).toBe("0.000");
  await page.getByRole("button",{name:"Registrar recepción",exact:true}).click();dialog=page.getByRole("dialog");await dialog.getByLabel("Referencia de entrega",{exact:true}).fill("REM-E2E-02");await dialog.getByLabel("Recibir Insumo de compra").fill("5.000");await dialog.getByRole("button",{name:"Confirmar recepción",exact:true}).click();await expect(dialog).toHaveCount(0);await expect(page.getByRole("button",{name:"Registrar recepción",exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"Registrar gasto asociado",exact:true}).click();dialog=page.getByRole("dialog");await dialog.getByLabel("Descripción",{exact:true}).fill("Compra documentada OC-E2E-01");await dialog.getByLabel("Importe neto",{exact:true}).fill("50.00");await dialog.getByLabel("Impuesto configurado (%)",{exact:true}).fill("21.00");await dialog.getByRole("button",{name:"Guardar borrador de gasto",exact:true}).click();await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("link",{name:"Compra documentada OC-E2E-01",exact:true})).toBeVisible();const associated=await (await page.request.get(`${api}${base}/expenses/?purchase_order=${id}`)).json();expect(associated.count).toBe(1);expect(associated.results[0].purchase_order).toBe(id);expect(associated.results[0].status).toBe("draft");
  await page.getByRole("button",{name:"Cerrar o cancelar pedido",exact:true}).click();dialog=page.getByRole("dialog");await dialog.getByLabel("Motivo",{exact:true}).fill("Recibido y revisado");await dialog.getByRole("button",{name:"Confirmar",exact:true}).click();await expect(dialog).toHaveCount(0);await expect(page.getByRole("button",{name:"Revertir recepción",exact:true})).toHaveCount(0);
  await checkAccessibility(page);await page.screenshot({path:artifactPath("purchase-detail-desktop.png"),fullPage:true});
  for(const width of [390,768]){await page.setViewportSize({width,height:900});await page.emulateMedia({reducedMotion:"reduce"});for(const route of ["purchases",`purchases/${id}`]){await page.goto(`/dashboard/${tenant.id}/${route}`);await expect(page.getByRole("heading",{level:1})).toBeVisible();await checkAccessibility(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:artifactPath(`${route.includes("/")?"purchase-detail":"purchases"}-${width}.png`),fullPage:true});}}
});

test("un pedido cancelado no cambia stock y el catálogo ajeno se rechaza desde la API real", async({page})=>{
  const tenant=await register(page);const base=`/api/tenants/${tenant.id}`;
  const supplier=await (await mutate(page.request,`${base}/suppliers/`,{name:"Proveedor de servicio"})).json();const product=await (await mutate(page.request,`${base}/products/`,{name:"Servicio de compra",product_type:"service",unit:"hour",unit_price:"10.00",tax_rate:"0.00",currency:"ARS"})).json();
  const response=await mutate(page.request,`${base}/purchases/`,{supplier:supplier.id,currency:"ARS",reference:"Cancelar sin entrega",lines:[{product:product.id,quantity:"1.000",unit_cost:"10.0000",tax_rate:"0.00"}]});expect(response.status()).toBe(201);const order=await response.json();
  await page.goto(`/dashboard/${tenant.id}/purchases/${order.id}`);await page.getByRole("button",{name:"Cerrar o cancelar pedido",exact:true}).click();const dialog=page.getByRole("dialog");await dialog.getByLabel("Motivo",{exact:true}).fill("Compra descartada");await dialog.getByRole("button",{name:"Confirmar",exact:true}).click();await expect(dialog).toHaveCount(0);await expect(page.getByRole("button",{name:"Confirmar pedido",exact:true})).toHaveCount(0);
  expect((await (await page.request.get(`${api}${base}/inventory/movements/`)).json()).count).toBe(0);
  expect((await mutate(page.request,`${base}/purchases/${order.id}/confirm/`,{})).status()).toBe(400);
  expect((await mutate(page.request,"/api/auth/logout/",{})).status()).toBe(200);
  const second=await register(page);expect((await page.request.get(`${api}/api/tenants/${second.id}/purchases/${order.id}/`)).status()).toBe(404);
  expect((await mutate(page.request,`/api/tenants/${second.id}/purchases/`,{supplier:supplier.id,currency:"ARS",lines:[{product:product.id,quantity:"1.000",unit_cost:"10.00",tax_rate:"0.00"}]})).status()).toBe(400);
});
