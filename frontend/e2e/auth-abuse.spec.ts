import { expect, test } from "./fixtures";
import { api, mutate } from "./support";

test("fuerza bruta local queda bloqueada sin abrir sesión ni aceptar headers falsificados", async ({ request }) => {
  for (let attempt = 0; attempt < 20; attempt++) {
    const response = await mutate(request, "/api/auth/login/", { email: "owner@e2e.example", password: "WrongSyntheticPassword!" }, "POST", { "X-Forwarded-For": `198.51.100.${attempt+1}`, "X-Client-IP": `198.51.100.${attempt+1}` });
    expect(response.status()).toBe(401);
  }
  const blocked = await mutate(request, "/api/auth/login/", { email: "owner@e2e.example", password: "SyntheticE2EPassword2026!" });
  expect(blocked.status()).toBe(429);
  expect(blocked.headers()["retry-after"]).toBe("900");
  expect((await request.get(`${api}/api/auth/me/`)).status()).toBe(401);
});
