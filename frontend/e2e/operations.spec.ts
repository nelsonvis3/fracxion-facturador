import { artifactPath, expect, test } from "./fixtures";
import { checkAccessibility } from "./accessibility";
import { api, mutate, register } from "./support";

test("proveedores persisten cambios y se desactivan sin eliminar su historia", async ({ page }) => {
  const tenant=await register(page);
  await page.goto(`/dashboard/${tenant.id}/suppliers`);
  await page.getByRole("button",{name:"Nuevo proveedor",exact:true}).click();
  const dialog=page.getByRole("dialog");
  await dialog.getByLabel("Nombre visible",{exact:true}).fill("Proveedor operativo");
  await dialog.getByLabel("Correo de contacto",{exact:true}).fill("supplier@example.com");
  await dialog.getByLabel("Identificación comercial",{exact:true}).fill("SYNTHETIC-1");
  await dialog.getByRole("button",{name:"Guardar proveedor"}).click();
  await expect(dialog).toHaveCount(0);
  const table=page.getByRole("region",{name:"Proveedores de la empresa"});
  await expect(table.getByRole("cell",{name:"Proveedor operativo",exact:true})).toBeVisible();
  await table.getByRole("button",{name:"Editar proveedor"}).click();
  await dialog.getByLabel("Teléfono",{exact:true}).fill("+54 370 4000000");
  await dialog.getByLabel("Proveedor activo",{exact:true}).uncheck();
  await dialog.getByRole("button",{name:"Guardar proveedor"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByText("No hay proveedores para estos filtros.")).toBeVisible();
  await page.getByRole("combobox",{name:"Estado",exact:true}).selectOption("false");
  await expect(table.getByText("Desactivado",{exact:true})).toBeVisible();
  await page.reload();await page.getByRole("combobox",{name:"Estado",exact:true}).selectOption("false");await expect(table.getByText("Desactivado",{exact:true})).toBeVisible();
  expect((await page.request.get(`${api}/api/tenants/${tenant.id}/suppliers/?is_active=false`)).status()).toBe(200);
  await checkAccessibility(page);
  await page.screenshot({path:artifactPath("suppliers-desktop.png"),fullPage:true});
});

test("inventario real bloquea stock negativo y revierte mediante un movimiento adicional", async ({page})=>{
  test.setTimeout(90000);
  const tenant=await register(page);const base=`/api/tenants/${tenant.id}`;
  const response=await mutate(page.request,`${base}/products/`,{name:"Producto de inventario",product_type:"product",unit:"unit",unit_price:"10.00",tax_rate:"0",currency:"ARS"});expect(response.status()).toBe(201);const product=await response.json();
  await page.goto(`/dashboard/${tenant.id}/inventory`);
  const items=page.getByRole("region",{name:"Existencias de productos"});
  await items.getByRole("button",{name:"Configurar",exact:true}).click();
  const dialog=page.getByRole("dialog");await dialog.getByLabel("Seguimiento habilitado").check();
  await dialog.getByLabel("Umbral de stock bajo",{exact:true}).fill("0");
  await dialog.getByRole("button",{name:"Guardar seguimiento"}).click();await expect(dialog).toHaveCount(0);
  async function fillMovement(kind:string,quantity:string,reason:string){
    await items.getByRole("button",{name:"Registrar movimiento",exact:true}).click();
    await dialog.getByRole("combobox",{name:"Movimiento",exact:true}).selectOption(kind);
    await dialog.getByLabel("Cantidad",{exact:true}).fill(quantity);await dialog.getByLabel("Motivo",{exact:true}).fill(reason);
    await dialog.getByRole("button",{name:"Confirmar movimiento"}).click();
  }
  await fillMovement("in","1","Ingreso físico inicial");await expect(dialog).toHaveCount(0);
  await expect(items.getByRole("cell",{name:"1.000",exact:true})).toBeVisible();
  await fillMovement("out","2","Intento que supera existencias");
  await expect(dialog.getByRole("alert").first()).toContainText("stock negativo");
  await dialog.getByLabel("Cantidad",{exact:true}).fill("1");await dialog.getByRole("button",{name:"Confirmar movimiento"}).click();await expect(dialog).toHaveCount(0);
  const history=page.getByRole("region",{name:"Movimientos de inventario"});
  const outgoing=history.getByRole("row").filter({has:page.getByRole("cell",{name:"Salida",exact:true})});
  await outgoing.getByRole("button",{name:"Revertir movimiento"}).click();
  await dialog.getByLabel("Motivo de reversión").fill("Despacho anulado");await dialog.getByRole("button",{name:"Confirmar reversión"}).click();await expect(dialog).toHaveCount(0);
  await expect(history.getByRole("cell",{name:"Reversión",exact:true})).toBeVisible();
  await expect(items.getByRole("cell",{name:"1.000",exact:true})).toBeVisible();
  const ledger=await page.request.get(`${api}${base}/inventory/movements/?product=${product.id}`);expect(ledger.status()).toBe(200);expect((await ledger.json()).count).toBe(3);
  await checkAccessibility(page);await page.screenshot({path:artifactPath("inventory-desktop.png"),fullPage:true});
  await page.emulateMedia({reducedMotion:"reduce"});
  for(const width of [768,390]){await page.setViewportSize({width,height:900});for(const route of ["inventory","suppliers"]){await page.goto(`/dashboard/${tenant.id}/${route}`);await expect(page.getByRole("heading",{level:1})).toBeVisible();await checkAccessibility(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:artifactPath(`${route}-${width}.png`),fullPage:true});}}
});
