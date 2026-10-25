import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { artifactPath,expect,test } from "./fixtures";
import { checkAccessibility } from "./accessibility";
import { api,register } from "./support";

test("verificación real de correo: solicitud, enlace firmado de QA, confirmación, estado y rechazo de repetición",async({page})=>{
  test.setTimeout(90000);
  await register(page);const me=await (await page.request.get(`${api}/api/auth/me/`)).json();
  await page.goto("/account/security");const section=page.getByRole("region",{name:"Verificación de correo",exact:true});await expect(section.getByText("Correo sin verificar",{exact:true})).toBeVisible();await section.getByRole("button",{name:"Enviar enlace de verificación",exact:true}).click();await expect(section.getByRole("status")).toContainText("aceptó el mensaje");
  // Unit tests inspect the actual memory-mail body. The browser process obtains
  // a signed fixture from the same synthetic DB, without a token-reading API.
  const token=execFileSync(process.env.E2E_PYTHON??resolve("../backend/.venv/bin/python"),["scripts/email_verification_e2e.py",String(me.user.id)],{cwd:resolve("../backend"),env:{...process.env,DJANGO_SETTINGS_MODULE:"config.e2e_settings"},encoding:"utf8"}).trim();
  await page.goto(`/verify-email#token=${token}`);await page.getByRole("button",{name:"Confirmar mi correo",exact:true}).click();await expect(page.getByRole("status")).toContainText("Correo verificado");await expect(page).toHaveURL(/\/verify-email$/);await checkAccessibility(page);
  await page.goto("/account/security");await expect(page.getByRole("region",{name:"Verificación de correo",exact:true}).getByText("Correo verificado",{exact:true})).toBeVisible();await expect(page.getByRole("button",{name:"Enviar enlace de verificación",exact:true})).toHaveCount(0);
  await page.goto(`/verify-email#token=${token}`);await page.getByRole("button",{name:"Confirmar mi correo",exact:true}).click();await expect(page.getByRole("main").getByRole("alert")).toContainText("no es válido");
  await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:"reduce"});await checkAccessibility(page);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);await page.screenshot({path:artifactPath("email-verification-mobile.png"),fullPage:true});
});
