import { chromium } from '../../../frontend/node_modules/playwright/index.mjs';
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile, stat } from 'node:fs/promises';
import { resolve, dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

const source = dirname(fileURLToPath(import.meta.url));
const docs = resolve(source, '../..');
const output = resolve(source, '..');
const frames = process.env.FRACXION_FRAMES || '/tmp/fracxion-video-frames';
const preview = process.argv.includes('--preview');
const benchmark = process.argv.includes('--benchmark');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.png': 'image/png', '.ttf': 'font/ttf', '.json': 'application/json' };
const server = createServer(async (req, res) => {
  const file = resolve(docs, '.' + decodeURIComponent(new URL(req.url, 'http://localhost').pathname));
  if (!file.startsWith(docs + '/') || !mime[extname(file)]) { res.writeHead(404); res.end(); return; }
  try { res.writeHead(200, { 'Content-Type': mime[extname(file)] }); res.end(await readFile(file)); }
  catch { res.writeHead(404); res.end(); }
});
await new Promise(resolve => server.listen(8769, '127.0.0.1', resolve));
let browser;
const errors = [];
try {
  const graphicsArgs = process.env.FRACXION_GPU === '1'
    ? ['--enable-gpu', '--ignore-gpu-blocklist', '--use-gl=angle', '--use-angle=gl', '--ozone-platform=headless']
    : ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'];
  browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage', ...graphicsArgs] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('response', response => { if (response.status() >= 400) errors.push(`HTTP ${response.status()}: ${response.url()}`); });
  await page.goto('http://127.0.0.1:8769/video/source/index.html', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => window.videoReady, { timeout: 30000 });
  const meta = await page.evaluate(() => window.videoMeta);
  meta.graphics = await page.evaluate(() => {
    const gl = document.querySelector('#scene').getContext('webgl2');
    const info = gl.getExtension('WEBGL_debug_renderer_info');
    return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  });
  await mkdir(output, { recursive: true });
  await mkdir(frames, { recursive: true });
  if (preview) {
    const samples = [0, 2.5, 5.5, 8.5, 11.5, 14.4, 16.5, 18.983333];
    const diagnostics = [];
    for (let i = 0; i < samples.length; i++) {
      diagnostics.push(await page.evaluate(t => window.renderFrame(t), samples[i]));
      await page.screenshot({ path: join(frames, `preview-${String(i).padStart(2, '0')}.png`), animations: 'disabled' });
    }
    if (errors.length) throw new Error(JSON.stringify(errors));
    await writeFile(join(frames, 'preview-diagnostics.json'), JSON.stringify({ ...meta, diagnostics, errors }, null, 2));
    console.log(JSON.stringify({ preview: frames, samples, errors }));
  } else {
    await page.locator('#scene').evaluate(el => { el.style.visibility = 'hidden'; });
    const plate = await page.screenshot({ type: 'png' });
    await page.locator('#scene').evaluate(el => { el.style.visibility = 'visible'; });
    await page.evaluate(data => window.prepareCapture(data), `data:image/png;base64,${plate.toString('base64')}`);
    if (benchmark) {
      const started = performance.now();
      for (let n = 0; n < 12; n++) {
        const result = await page.evaluate(t => window.captureFrame(t), n / 60);
        if (n === 11) await writeFile(join(frames, 'capture-benchmark.jpg'), Buffer.from(result.jpeg, 'base64'));
      }
      console.log(JSON.stringify({ frames: 12, seconds: (performance.now() - started) / 1000, graphics: meta.graphics, errors }));
    } else {
    const total = meta.duration * meta.fps;
    const silent = join(frames, 'silent.mp4');
    const encoder = spawn('ffmpeg', ['-hide_banner', '-loglevel', 'warning', '-y', '-f', 'image2pipe', '-framerate', String(meta.fps), '-vcodec', 'mjpeg', '-i', 'pipe:0', '-an', '-vf', 'scale=in_range=pc:out_range=tv:out_color_matrix=bt709', '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-threads', '4', '-pix_fmt', 'yuv420p', '-color_range', 'tv', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-r', String(meta.fps), '-movflags', '+faststart', silent], { stdio: ['pipe', 'inherit', 'inherit'] });
    const encodingDone = once(encoder, 'exit');
    const diagnostics = [];
    for (let n = 0; n < total; n++) {
      const { state, jpeg } = await page.evaluate(t => window.captureFrame(t), n / meta.fps);
      if (!state.webgl) throw new Error(`WebGL perdido en fotograma ${n}`);
      const frame = Buffer.from(jpeg, 'base64');
      if (!encoder.stdin.write(frame)) await once(encoder.stdin, 'drain');
      diagnostics.push({ frame: n, ...state });
      if (n % 60 === 0) console.log(`Render ${n}/${total} (${(n / meta.fps).toFixed(1)} s)`);
    }
    encoder.stdin.end();
    const [exitCode] = await encodingDone;
    if (exitCode !== 0 || errors.length) throw new Error(JSON.stringify({ exitCode, errors }));
    await writeFile(join(output, 'render-diagnostics.json'), JSON.stringify({ ...meta, frames: total, errors, diagnostics }, null, 2));
    console.log(JSON.stringify({ silent, bytes: (await stat(silent)).size, frames: total, errors }));
    }
  }
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
