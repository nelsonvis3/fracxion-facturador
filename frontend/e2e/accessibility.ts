import type { Page } from "@playwright/test";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import type { AxeResults, RunOptions } from "axe-core";
import { expect } from "@playwright/test";

const axePath = createRequire(resolve(process.cwd(), "package.json")).resolve("axe-core/axe.min.js");
export async function checkAccessibility(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.addScriptTag({ path: axePath });
  const result = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (target: Document, options: RunOptions) => Promise<AxeResults> } }).axe;
    return axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] } });
  });
  expect(result.violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })), "Comprobaciones automáticas de accesibilidad; no sustituyen revisión manual").toEqual([]);
}
