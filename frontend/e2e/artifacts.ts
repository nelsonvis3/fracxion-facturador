import { mkdirSync } from "node:fs";
import { dirname, resolve, sep } from "node:path";
import { tmpdir } from "node:os";

export function artifactPath(name: string) {
  const root = resolve(process.env.E2E_ARTIFACT_DIR ?? resolve(tmpdir(), "fracxion-e2e-artifacts"));
  const target = resolve(root, name);
  if (!target.startsWith(root + sep)) throw new Error("El artefacto debe quedar dentro del directorio de pruebas.");
  mkdirSync(dirname(target), { recursive: true });
  return target;
}
