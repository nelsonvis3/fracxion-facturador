import { copyFileSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { getHyperframeRuntimeScript } from "@hyperframes/core/runtime-script";

const require = createRequire(import.meta.url);
const directory = new URL("../public/hyperframes/vendor/", import.meta.url);
mkdirSync(directory, { recursive: true });
copyFileSync(require.resolve("gsap/dist/gsap.min.js"), new URL("gsap.min.js", directory));
writeFileSync(new URL("hyperframes-runtime.js", directory), getHyperframeRuntimeScript());
console.log(`Hyperframes: assets locales preparados en ${fileURLToPath(directory)}`);
