import { createHmac } from "node:crypto";
import { artifactPath, expect, test } from "./fixtures";
import { checkAccessibility } from "./accessibility";
import { api, mutate, register } from "./support";

function totp(secret: string) {
  const alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits=secret.split("").map(char=>alphabet.indexOf(char).toString(2).padStart(5,"0")).join("");
  const key=Buffer.from(bits.match(/.{8}/g)!.map(byte=>parseInt(byte,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const hash=createHmac("sha1",key).update(counter).digest();const offset=hash[19]&15;
  return ((hash.readUInt32BE(offset)&0x7fffffff)%1000000).toString().padStart(6,"0");
}

test("MFA real: activar, invalidar otro acceso, login con recuperación, rechazar repetición y desactivar",async({page,browser})=>{
  test.setTimeout(120000);
  await register(page);
  const me=await(await page.request.get(`${api}/api/auth/me/`)).json();
  const other=await browser.newContext();
  try {
    expect((await mutate(other.request,"/api/auth/login/",{email:me.user.email,password:"SyntheticEnterprisePassword2026!"})).status()).toBe(200);
    await page.goto("/account/security");
    const section=page.getByRole("region",{name:"Autenticación en dos pasos",exact:true});
    await section.getByLabel("Contraseña actual para MFA",{exact:true}).fill("SyntheticEnterprisePassword2026!");
    await section.getByRole("button",{name:"Configurar MFA",exact:true}).click();
    const secret=(await section.getByLabel("Clave del autenticador",{exact:true}).innerText()).trim();
    await section.getByLabel("Código MFA o de recuperación",{exact:true}).fill(totp(secret));
    await section.getByRole("button",{name:"Confirmar activación MFA",exact:true}).click();
    await expect(section.getByText("Activada",{exact:true})).toBeVisible();
    const codes=(await section.getByLabel("Códigos de recuperación",{exact:true}).innerText()).trim().split("\n");
    expect(codes).toHaveLength(8);
    expect((await other.request.get(`${api}/api/auth/me/`)).status()).toBe(401);
    await expect(page.getByRole("region",{name:"Sesiones de mi cuenta",exact:true}).getByRole("row")).toHaveCount(2);
    await section.getByRole("button",{name:"Ya los guardé, ocultar códigos",exact:true}).click();
    await checkAccessibility(page);
    await page.setViewportSize({width:390,height:844});await checkAccessibility(page);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.screenshot({path:artifactPath("mfa-enabled-mobile.png"),fullPage:true});
    expect((await mutate(page.request,"/api/auth/logout/",{})).status()).toBe(200);
    await page.goto("/");
    const skip=page.getByRole("button",{name:"Omitir introducción",exact:true});if(await skip.isVisible())await skip.click();
    await page.getByLabel("Correo electrónico",{exact:true}).fill(me.user.email);
    await page.getByLabel("Contraseña",{exact:true}).fill("SyntheticEnterprisePassword2026!");
    await page.getByRole("button",{name:"Iniciar sesión",exact:true}).click();
    await expect(page.getByLabel("Código MFA o de recuperación",{exact:true})).toBeVisible();
    await expect(page.getByLabel("Código MFA o de recuperación",{exact:true})).toBeFocused();
    expect((await page.request.get(`${api}/api/auth/me/`)).status()).toBe(401);
    await page.getByLabel("Código MFA o de recuperación",{exact:true}).fill(codes[0]);
    await page.getByRole("button",{name:"Verificar y entrar",exact:true}).click();
    await expect(page.getByRole("link",{name:/Abrir el espacio de trabajo/})).toBeVisible({timeout:12000});
    const challenge=await mutate(other.request,"/api/auth/login/",{email:me.user.email,password:"SyntheticEnterprisePassword2026!"});
    expect((await challenge.json()).mfa_required).toBe(true);
    expect((await mutate(other.request,"/api/auth/mfa/login/",{code:codes[0]})).status()).toBe(401);
    await page.goto("/account/security");
    await section.getByLabel("Contraseña actual para MFA",{exact:true}).fill("SyntheticEnterprisePassword2026!");
    await section.getByLabel("Código MFA o de recuperación",{exact:true}).fill(codes[1]);
    page.once("dialog",dialog=>dialog.accept());
    await section.getByRole("button",{name:"Desactivar MFA",exact:true}).click();
    await expect(section.getByText("Desactivada",{exact:true})).toBeVisible();
  } finally { await other.close(); }
});
