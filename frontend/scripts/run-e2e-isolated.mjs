// Keep the real security limits: each spec gets a fresh, private test API process.
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { existsSync, readdirSync, mkdtempSync, createWriteStream, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as wait } from "node:timers/promises";

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backend = resolve(frontend, "../backend");
const args = process.argv.slice(2);
const requested = args.filter(arg => arg.endsWith(".spec.ts"));
const options = args.filter(arg => !requested.includes(arg));
const files = requested.length ? requested : readdirSync(join(frontend, "e2e")).filter(name => name.endsWith(".spec.ts")).sort().map(name => `e2e/${name}`);
if (process.env.DJANGO_ENV === "production" || !["127.0.0.1", "localhost"].includes(process.env.DB_HOST ?? "127.0.0.1")) throw Error("E2E requiere PostgreSQL de pruebas local y configuración de desarrollo explícita.");
await new Promise((resolveReady, reject) => {
  const probe = createServer(); probe.once("error", () => reject(Error("El puerto 8001 está ocupado. Detené solo tu API de pruebas antes de ejecutar E2E."))); probe.listen(8001, "127.0.0.1", () => probe.close(resolveReady));
});
const output = mkdtempSync(join(tmpdir(), "fracxion-e2e-"));
const python = process.env.E2E_PYTHON ?? (existsSync(join(backend, ".venv/bin/python")) ? join(backend, ".venv/bin/python") : "python");
let activeApi;
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => { activeApi?.kill("SIGTERM"); process.exit(signal === "SIGINT" ? 130 : 143); });
let failed = false;
for (const file of files) {
  const name = file.replaceAll(/[^a-zA-Z0-9.-]/g, "_");
  const logPath = join(output, `${name}.txt`);
  const log = createWriteStream(logPath);
  const api = spawn(python, ["manage.py", "runserver", "127.0.0.1:8001", "--settings=config.e2e_settings", "--noreload"], { cwd: backend, env: { ...process.env, DJANGO_ENV: "development", DJANGO_DEBUG: "False", DJANGO_SETTINGS_MODULE: "config.e2e_settings", PYTHONUNBUFFERED: "1" }, stdio: ["ignore", "pipe", "pipe"] });
  activeApi = api; api.stdout.pipe(log, { end: false }); api.stderr.pipe(log, { end: false }); api.on("error", error => log.write(error.message));
  try {
    let ready = false;
    for (let n = 0; n < 50; n++) {
      if (api.exitCode !== null) break;
      try { if ((await fetch("http://127.0.0.1:8001/ready/", { signal: AbortSignal.timeout(1000) })).ok) { ready = true; break; } } catch { /* Startup can briefly refuse connections. */ }
      await wait(200);
    }
    if (!ready) throw Error(`La API sintética no inició. Revisá ${logPath}`);
    console.log(`\nAPI de pruebas aislada · ${file}`);
    const test = spawn(process.execPath, [join(frontend, "node_modules/@playwright/test/cli.js"), "test", file, ...options], { cwd: frontend, env: { ...process.env, E2E_PYTHON: python, E2E_ARTIFACT_DIR: join(output, "screenshots") }, stdio: "inherit" });
    const code = await new Promise((resolveExit, reject) => { test.once("error", reject); test.once("exit", resolveExit); });
    if (code !== 0) failed = true;
  } catch (error) { console.error(error.message); failed = true; }
  finally {
    api.kill("SIGTERM");
    if (api.exitCode === null && api.signalCode === null) await Promise.race([new Promise(resolveExit => api.once("exit", resolveExit)), wait(3000)]);
    if (api.exitCode === null && api.signalCode === null) api.kill("SIGKILL");
    activeApi = undefined; log.end();
  }
  if (failed) { console.error(readFileSync(logPath, "utf8").split("\n").slice(-20).join("\n")); break; }
}
console.log(`Registros de API de pruebas: ${output}`);
process.exitCode = failed ? 1 : 0;
