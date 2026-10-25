import { test as base, expect } from "@playwright/test";

export const test = base.extend<{ browserErrors: void }>({
  browserErrors: [async ({ page }, use) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("response", response => {
      if (response.status() >= 500) {
        errors.push(`HTTP ${response.status()}: ${new URL(response.url()).pathname}`);
      }
    });
    await use();
    expect(errors, "Excepciones JavaScript y respuestas 5xx del flujo").toEqual([]);
  }, { auto: true }],
});

export { expect } from "@playwright/test";
export { artifactPath } from "./artifacts";
