import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { ESLint } from 'eslint';

const require = createRequire(import.meta.url);
const pluginRequire = createRequire(require.resolve('@next/eslint-plugin-next'));
const { getRootDirs } = pluginRequire('./utils/get-root-dirs.js');
const nextPlugin = require('@next/eslint-plugin-next');

test('the Next-only fast-glob alias is the maintained tinyglobby implementation', () => {
  assert.equal(pluginRequire('fast-glob/package.json').name, 'tinyglobby');
});

test('Next rules still detect internal HTML links for literal, glob and array roots', async () => {
  const root = mkdtempSync(join(tmpdir(), 'fracxion-eslint-'));
  try {
    for (const name of ['one', 'two']) {
      mkdirSync(join(root, name, 'pages'), { recursive: true });
      writeFileSync(join(root, name, 'pages', 'index.js'), 'export default function Home() { return null; }');
    }
    for (const pattern of [join(root, 'one'), join(root, '*'), [join(root, 'one'), join(root, 'two')]]) {
      const dirs = getRootDirs({ cwd: root, settings: { next: { rootDir: pattern } } }).map(dir => resolve(dir));
      assert.ok(dirs.includes(join(root, 'one')));
      if (Array.isArray(pattern) || pattern.endsWith('*')) assert.ok(dirs.includes(join(root, 'two')));
      const lint = new ESLint({ overrideConfigFile: true, overrideConfig: [{
        files: ['**/*.js'], languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
        plugins: { '@next/next': nextPlugin }, settings: { next: { rootDir: pattern } },
        rules: { '@next/next/no-html-link-for-pages': 'error' },
      }] });
      const [bad] = await lint.lintText('export default () => <a href="/">Home</a>', { filePath: 'contract.js' });
      assert.equal(bad.errorCount, 1);
      assert.equal(bad.messages[0].ruleId, '@next/next/no-html-link-for-pages');
      const [good] = await lint.lintText('export default () => <a href="https://example.org">External</a>', { filePath: 'contract.js' });
      assert.equal(good.errorCount, 0);
    }
  } finally { rmSync(root, { recursive: true, force: true }); }
});
