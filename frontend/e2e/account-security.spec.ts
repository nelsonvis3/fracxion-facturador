import { artifactPath,expect,test } from "./fixtures";
import { checkAccessibility } from "./accessibility";
import { api,mutate,register } from "./support";

test("dos navegadores: revocar sesiones, cambiar contraseña y conservar el acceso actual",async({page,browser})=>{
  test.setTimeout(90000);
  const tenant=await register(page);
  const me=await (await page.request.get(`${api}/api/auth/me/`)).json();
  const other=await browser.newContext();const another=await other.newPage();
  try{
    let login=await mutate(other.request,"/api/auth/login/",{email:me.user.email,password:"SyntheticEnterprisePassword2026!"});expect(login.status()).toBe(200);
    await page.goto(`/dashboard/${tenant.id}`);await page.getByRole("link",{name:"Seguridad de mi cuenta",exact:true}).click();
    await expect(page.getByRole("heading",{name:"Seguridad de mi cuenta",exact:true})).toBeVisible();
    await expect(page.getByRole("button",{name:"Cerrar sesión de este dispositivo",exact:true})).toHaveCount(1);
    await page.getByRole("button",{name:"Cerrar otras sesiones",exact:true}).click();const dialog=page.getByRole("dialog");await dialog.getByLabel("Contraseña actual",{exact:true}).fill("SyntheticEnterprisePassword2026!");await dialog.getByRole("button",{name:"Confirmar cierre de otras sesiones",exact:true}).click();await expect(dialog).toHaveCount(0);
    expect((await other.request.get(`${api}/api/auth/me/`)).status()).toBe(401);expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(200);
    login=await mutate(other.request,"/api/auth/login/",{email:me.user.email,password:"SyntheticEnterprisePassword2026!"});expect(login.status()).toBe(200);
    await page.getByRole("button",{name:"Actualizar sesiones",exact:true}).click();
    const form=page.getByRole("form",{name:"Cambiar contraseña",exact:true});await form.getByLabel("Contraseña actual",{exact:true}).fill("wrong");await form.getByLabel("Nueva contraseña",{exact:true}).fill("SyntheticChangedPassword2026!");await form.getByLabel("Confirmar nueva contraseña",{exact:true}).fill("SyntheticChangedPassword2026!");await form.getByRole("button",{name:"Guardar contraseña",exact:true}).click();await expect(page.getByRole("main").getByRole("alert").first()).toContainText("contraseña actual");
    await form.getByLabel("Contraseña actual",{exact:true}).fill("SyntheticEnterprisePassword2026!");await form.getByRole("button",{name:"Guardar contraseña",exact:true}).click();await expect(page.getByRole("status").filter({hasText:"Contraseña actualizada"})).toContainText("Contraseña actualizada");
    expect((await other.request.get(`${api}/api/auth/me/`)).status()).toBe(401);expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(200);
    expect((await mutate(other.request,"/api/auth/login/",{email:me.user.email,password:"SyntheticEnterprisePassword2026!"})).status()).toBe(401);
    expect((await mutate(other.request,"/api/auth/login/",{email:me.user.email,password:"SyntheticChangedPassword2026!"})).status()).toBe(200);
    await another.goto(`/dashboard/${tenant.id}`);await expect(another.getByRole("heading",{level:1})).toBeVisible();
    await checkAccessibility(page);await page.screenshot({path:artifactPath("account-security-desktop.png"),fullPage:true});
    await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:"reduce"});await checkAccessibility(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:artifactPath("account-security-mobile.png"),fullPage:true});
  }finally{await other.close();}
});
