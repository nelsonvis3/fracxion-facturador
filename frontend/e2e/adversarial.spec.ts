import { expect, test } from "./fixtures";
import { api, mutate, register } from "./support";

test("ataques controlados a configuración, miembros, invitaciones y análisis no filtran empresas", async ({ page, playwright }) => {
  const first = await register(page);
  const outsider = await playwright.request.newContext();
  try {
    const email = `outsider.${Date.now()}@e2e.example`;
    const signup = await mutate(outsider, "/api/auth/register/", { first_name: "Other", company_name: "Empresa ajena sintética", email, password: "SyntheticOutsiderPassword2026!", password_confirm: "SyntheticOutsiderPassword2026!" });
    expect(signup.status()).toBe(201); const other = (await signup.json()).tenant;
    for (const resource of ["settings/", "settings/logo/", "members/", "invitations/", "analytics/overview/", "analytics/records/"]) {
      const denied = await page.request.get(`${api}/api/tenants/${other.id}/${resource}`);
      expect(denied.status()).toBe(403); expect(await denied.text()).not.toContain("Empresa ajena sintética");
    }
    const members = await (await outsider.get(`${api}/api/tenants/${other.id}/members/`)).json();
    const foreignId = members.results[0].id;
    expect((await mutate(page.request, `/api/tenants/${first.id}/members/${foreignId}/`, { role: "owner" }, "PATCH")).status()).toBe(404);
    for (const payload of [{ is_superuser: true }, { tenant: other.id }, { logo_data: "<svg onload='alert(1)'/>" }, { timezone: "../../etc/passwd" }, { payment_terms_days: -100 }, { default_currency: "ZZZ" }]) {
      expect((await mutate(page.request, `/api/tenants/${first.id}/settings/`, payload, "PATCH")).status()).toBe(400);
    }
    const csrf = (await (await page.request.get(`${api}/api/auth/csrf/`)).json()).csrfToken;
    expect((await page.request.patch(`${api}/api/tenants/${first.id}/settings/`, { headers: { Origin: "https://foreign.example", "X-CSRFToken": csrf }, data: { name: "Untrusted origin" } })).status()).toBe(403);
    const identity = await (await page.request.get(`${api}/api/auth/me/`)).json();
    expect(identity.user).not.toHaveProperty("is_superuser");
  } finally { await outsider.dispose(); }
});
