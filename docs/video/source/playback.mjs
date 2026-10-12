import { chromium } from '../../../frontend/node_modules/playwright/index.mjs';
import { createServer } from 'node:http';
import { writeFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const file = resolve(root, 'fracxion-comercial-3d-dinamico.mp4');
const bytes = (await stat(file)).size;
const server = createServer((req, res) => {
  if (req.url === '/') {
    res.writeHead(200, { 'Content-Type': 'text/html' });
    res.end('<!doctype html><html lang="es"><meta charset="utf-8"><title>Revisión del MP4</title><style>body{margin:0;background:#eeeaf6}video{display:block;width:1920px;height:1080px}</style><video src="/video.mp4" muted playsinline preload="auto"></video></html>');
  } else if (req.url === '/video.mp4') {
    if (req.headers.range) {
      const parts = /bytes=(\d+)-(\d*)/.exec(req.headers.range);
      if (!parts) { res.writeHead(416); res.end(); return; }
      const start = Number(parts[1]);
      const end = parts[2] ? Math.min(Number(parts[2]), bytes - 1) : bytes - 1;
      if (start > end || start >= bytes) { res.writeHead(416); res.end(); return; }
      res.writeHead(206, { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Content-Range': `bytes ${start}-${end}/${bytes}`, 'Content-Length': end - start + 1 });
      createReadStream(file, { start, end }).pipe(res);
    } else {
      res.writeHead(200, { 'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Content-Length': bytes });
      createReadStream(file).pipe(res);
    }
  } else { res.writeHead(204); res.end(); }
});
await new Promise(resolve => server.listen(8770, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true, ...(process.env.FRACXION_FULL_CHROME === '1' ? { channel: 'chromium' } : {}), args: ['--no-sandbox', '--disable-gpu', '--disable-accelerated-video-decode', '--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('http://127.0.0.1:8770/');
  try { await page.waitForFunction(() => document.querySelector('video').readyState >= 3); }
  catch (error) {
    console.log(await page.evaluate(() => { const v = document.querySelector('video'); return { error: v.error?.message, code: v.error?.code, readyState: v.readyState, h264: v.canPlayType('video/mp4; codecs="avc1.64002a"'), aac: v.canPlayType('audio/mp4; codecs="mp4a.40.2"') }; }));
    throw error;
  }
  const metadata = await page.evaluate(() => { const v = document.querySelector('video'); return { duration: v.duration, width: v.videoWidth, height: v.videoHeight }; });
  console.log(JSON.stringify({ metadata }));
  if (metadata.duration !== 19 || metadata.width !== 1920 || metadata.height !== 1080) throw new Error(JSON.stringify(metadata));
  const samples = [];
  for (const time of [0, 5, 10, 18.9]) {
    await page.evaluate(time => new Promise((resolve, reject) => {
      const video = document.querySelector('video');
      if (Math.abs(video.currentTime - time) < 0.005) { resolve(); return; }
      video.addEventListener('seeked', () => resolve(), { once: true });
      video.addEventListener('error', () => reject(new Error('Error de decodificación')), { once: true });
      video.currentTime = time;
    }), time);
    samples.push(await page.evaluate(() => { const v = document.querySelector('video'); return { time: v.currentTime, readyState: v.readyState, error: v.error?.message || null }; }));
  }
  await page.evaluate(() => { document.querySelector('video').currentTime = 0; });
  await page.waitForFunction(() => { const v = document.querySelector('video'); return v.readyState >= 3 && !v.seeking; });
  const playback = await page.evaluate(async () => {
    const video = document.querySelector('video');
    const started = performance.now();
    const initialQuality = video.getVideoPlaybackQuality();
    let waiting = 0;
    let stalled = 0;
    video.addEventListener('waiting', () => waiting++);
    video.addEventListener('stalled', () => stalled++);
    const ended = new Promise((resolve, reject) => { video.addEventListener('ended', resolve, { once: true }); video.addEventListener('error', () => reject(new Error(video.error.message)), { once: true }); setTimeout(() => reject(new Error(`La reproducción no terminó: ${video.currentTime}`)), 26000); });
    await video.play();
    await ended;
    const quality = video.getVideoPlaybackQuality();
    return { ended: video.ended, currentTime: video.currentTime, playbackRate: video.playbackRate, wallSeconds: (performance.now() - started) / 1000, totalVideoFrames: quality.totalVideoFrames - initialQuality.totalVideoFrames, droppedVideoFrames: quality.droppedVideoFrames - initialQuality.droppedVideoFrames, waitingEvents: waiting, stalledEvents: stalled, error: video.error?.message || null };
  });
  if (!playback.ended || playback.error || playback.playbackRate !== 1 || errors.length) throw new Error(JSON.stringify({ playback, errors }));
  const report = { metadata, samples, playback, errors };
  await writeFile(resolve(root, 'revision-reproduccion.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
