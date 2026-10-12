import * as THREE from 'three';
import { RoomEnvironment } from './vendor/RoomEnvironment.js';

export const DURATION = 19;
const W = 1575;
const H = 905;
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xeeeaf6, 23, 65);
const renderer = new THREE.WebGLRenderer({ canvas: document.querySelector('#scene'), alpha: true, antialias: true, preserveDrawingBuffer: true });
renderer.setSize(W, H, false);
renderer.setPixelRatio(1);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.2;
const camera = new THREE.PerspectiveCamera(33, W / H, 0.1, 100);
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.06).texture;
scene.environmentIntensity = 0.65;
scene.add(new THREE.HemisphereLight(0xffffff, 0xafa1c1, 2.3));
const key = new THREE.DirectionalLight(0xfff6ed, 4.5);
key.position.set(-5, 11, 8);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: 1, far: 35 });
key.shadow.bias = -0.0002;
key.shadow.normalBias = 0.025;
key.shadow.radius = 5;
scene.add(key);
const rim = new THREE.DirectionalLight(0xd6cbff, 3);
rim.position.set(8, 5, -5);
scene.add(rim);
const fill = new THREE.DirectionalLight(0xffffff, 1.3);
fill.position.set(4, 4, 10);
scene.add(fill);

const ground = new THREE.Mesh(new THREE.PlaneGeometry(160, 160), new THREE.ShadowMaterial({ color: 0x65507e, opacity: 0.16 }));
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

function shape(w, h, r) {
  const x = -w / 2;
  const y = -h / 2;
  const s = new THREE.Shape();
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}
function body(w, h, d, r, material) {
  const geometry = new THREE.ExtrudeGeometry(shape(w, h, r), { depth: d, bevelEnabled: true, bevelSegments: 3, steps: 1, bevelSize: Math.min(d / 5, 0.024), bevelThickness: Math.min(d / 5, 0.024), curveSegments: 10 });
  geometry.translate(0, 0, -d / 2);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  return mesh;
}
function screen(w, h, r, texture) {
  const geometry = new THREE.ShapeGeometry(shape(w, h, r), 18);
  const uv = geometry.attributes.uv;
  const pos = geometry.attributes.position;
  for (let i = 0; i < pos.count; i++) uv.setXY(i, pos.getX(i) / w + 0.5, pos.getY(i) / h + 0.5);
  return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ map: texture, toneMapped: false }));
}
const alu = new THREE.MeshStandardMaterial({ color: 0xa3a1b0, metalness: 0.88, roughness: 0.27 });
const paleAlu = new THREE.MeshStandardMaterial({ color: 0xd7d4e0, metalness: 0.72, roughness: 0.33 });
const dark = new THREE.MeshStandardMaterial({ color: 0x12121a, roughness: 0.45, metalness: 0.26 });
const keysMaterial = new THREE.MeshStandardMaterial({ color: 0x23222c, metalness: 0.12, roughness: 0.63 });
const black = new THREE.MeshStandardMaterial({ color: 0x06060d, roughness: 0.26, metalness: 0.35 });

const image = src => new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error(`No se pudo cargar ${src}`)); img.src = src; });
const captureNames = ['dashboard-desktop', 'customers', 'invoice-builder', 'invoice-issued', 'invoice-paid', 'dashboard-mobile-full', 'payment-mobile', 'payment-mobile-submit', 'payment-result-mobile'];
const captureImages = await Promise.all(captureNames.map(name => image(`./demo-captures/${name}.png`)));
const captures = Object.fromEntries(captureNames.map((name, i) => [name, captureImages[i]]));
const captureEvidence = await fetch('./demo-captures/capture-evidence.json').then(response => response.json());
const laptopCanvas = Object.assign(document.createElement('canvas'), { width: 1440, height: 900 });
const laptopCtx = laptopCanvas.getContext('2d');
const laptopTexture = new THREE.CanvasTexture(laptopCanvas);
laptopTexture.colorSpace = THREE.SRGBColorSpace;
laptopTexture.anisotropy = renderer.capabilities.getMaxAnisotropy();
const phoneCanvas = Object.assign(document.createElement('canvas'), { width: 780, height: 1688 });
const phoneCtx = phoneCanvas.getContext('2d');
const phoneTexture = new THREE.CanvasTexture(phoneCanvas);
phoneTexture.colorSpace = THREE.SRGBColorSpace;
phoneTexture.anisotropy = renderer.capabilities.getMaxAnisotropy();

const laptop = new THREE.Group();
laptop.position.set(-0.83, 0.09, -0.25);
laptop.rotation.y = -0.11;
scene.add(laptop);
const base = body(6.8, 4.4, 0.16, 0.22, alu);
base.rotation.x = -Math.PI / 2;
base.position.set(0, 0.12, 0.30);
laptop.add(base);
const deck = body(6.74, 4.31, 0.033, 0.20, paleAlu);
deck.rotation.x = -Math.PI / 2;
deck.position.set(0, 0.23, 0.29);
laptop.add(deck);
const keyboardWell = body(5.63, 1.91, 0.026, 0.12, dark);
keyboardWell.rotation.x = -Math.PI / 2;
keyboardWell.position.set(0, 0.26, -0.61);
laptop.add(keyboardWell);
const keyGeo = new THREE.ExtrudeGeometry(shape(0.34, 0.285, 0.035), { depth: 0.025, bevelEnabled: false, curveSegments: 3 });
const keyLabels = [];
for (let row = 0; row < 5; row++) {
  for (let col = 0; col < 14; col++) {
    if (row === 4 && col > 3 && col < 10) continue;
    const keyMesh = new THREE.Mesh(keyGeo, keysMaterial);
    keyMesh.rotation.x = -Math.PI / 2;
    keyMesh.position.set(-2.52 + col * 0.389, 0.29, -1.31 + row * 0.345);
    laptop.add(keyMesh);
    if (row > 0 && row < 4 && col > 0 && col < 13) keyLabels.push({ x: keyMesh.position.x, z: keyMesh.position.z, char: ['QWERTYUIOP[]', 'ASDFGHJKL;  ', 'ZXCVBNM,./  '][row - 1][col - 1] });
  }
}
const space = body(2.29, 0.285, 0.025, 0.045, keysMaterial);
space.rotation.x = -Math.PI / 2;
space.position.set(0, 0.305, 0.071);
laptop.add(space);
const labelCanvas = Object.assign(document.createElement('canvas'), { width: 1400, height: 470 });
const labelCtx = labelCanvas.getContext('2d');
labelCtx.font = '18px Studio'; labelCtx.fillStyle = '#aaaaaf'; labelCtx.textAlign = 'center'; labelCtx.textBaseline = 'middle';
for (const k of keyLabels) labelCtx.fillText(k.char, (k.x / 5.63 + 0.5) * 1400, ((k.z + 0.61) / 1.91 + 0.5) * 470);
const labelTexture = new THREE.CanvasTexture(labelCanvas);
const labels = new THREE.Mesh(new THREE.PlaneGeometry(5.63, 1.91), new THREE.MeshBasicMaterial({ map: labelTexture, transparent: true, depthWrite: false }));
labels.rotation.x = -Math.PI / 2;
labels.position.set(0, 0.32, -0.61);
laptop.add(labels);
const trackBorder = body(2.56, 1.26, 0.013, 0.095, alu);
trackBorder.rotation.x = -Math.PI / 2;
trackBorder.position.set(0, 0.253, 1.24);
laptop.add(trackBorder);
const trackpad = body(2.50, 1.20, 0.014, 0.078, paleAlu);
trackpad.rotation.x = -Math.PI / 2;
trackpad.position.set(0, 0.264, 1.24);
laptop.add(trackpad);
const hinge = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 6.1, 20), dark);
hinge.rotation.z = Math.PI / 2;
hinge.position.set(0, 0.29, -1.67);
laptop.add(hinge);
const lid = new THREE.Group();
lid.position.set(0, 0.28, -1.69);
lid.rotation.x = -0.16;
laptop.add(lid);
const lidBack = body(6.7, 4.30, 0.14, 0.18, alu);
lidBack.position.y = 2.15;
lid.add(lidBack);
const bezel = body(6.58, 4.18, 0.046, 0.14, black);
bezel.position.set(0, 2.16, 0.087);
lid.add(bezel);
const laptopDisplay = screen(6.18, 3.8625, 0.045, laptopTexture);
laptopDisplay.position.set(0, 2.16, 0.134);
lid.add(laptopDisplay);
const webcam = new THREE.Mesh(new THREE.CircleGeometry(0.021, 18), new THREE.MeshBasicMaterial({ color: 0x3c3c54 }));
webcam.position.set(0, 4.19, 0.135);
lid.add(webcam);
// Only physical edge reflections; no animated glare over the website.
const phone = new THREE.Group();
phone.position.set(4.05, 0.17, 0.78);
phone.scale.setScalar(0.80);
phone.rotation.set(0, -0.10, -0.018);
scene.add(phone);
const phoneBody = body(2.69, 5.80, 0.22, 0.34, alu);
phoneBody.position.y = 2.9;
phone.add(phoneBody);
const phoneFront = body(2.60, 5.70, 0.064, 0.30, black);
phoneFront.position.set(0, 2.90, 0.127);
phone.add(phoneFront);
const phoneDisplay = screen(2.45, 5.30205, 0.22, phoneTexture);
phoneDisplay.position.set(0, 2.88, 0.193);
phone.add(phoneDisplay);
const island = body(0.70, 0.14, 0.014, 0.07, black);
island.position.set(0, 5.50, 0.205);
phone.add(island);
const phoneLens = new THREE.Mesh(new THREE.CircleGeometry(0.030, 20), new THREE.MeshStandardMaterial({ color: 0x212a49, metalness: 0.7, roughness: 0.18 }));
phoneLens.position.set(0.25, 5.50, 0.219);
phone.add(phoneLens);
const home = body(0.80, 0.035, 0.008, 0.017, new THREE.MeshBasicMaterial({ color: 0xc9c8d5 }));
home.position.set(0, 0.107, 0.177);
phone.add(home);
for (const [y, h, x] of [[4.17, 0.65, -1.36], [3.39, 0.41, -1.36], [4.0, 0.77, 1.36]]) {
  const button = body(0.035, h, 0.10, 0.017, alu);
  button.position.set(x, y, 0);
  phone.add(button);
}

const clamp = x => Math.max(0, Math.min(1, x));
const smooth = x => { x = clamp(x); return x * x * x * (x * (x * 6 - 15) + 10); };
// Linear motion in the middle; half-cosine ramps keep velocity continuous.
function paced(t, start, end, ramp = 1.3) {
  const duration = end - start;
  let u = Math.max(0, Math.min(duration, t - start));
  const distance = duration - ramp;
  if (u < ramp) return (u / 2 - ramp * Math.sin(Math.PI * u / ramp) / (2 * Math.PI)) / distance;
  if (u > duration - ramp) { const v = duration - u; return 1 - (v / 2 - ramp * Math.sin(Math.PI * v / ramp) / (2 * Math.PI)) / distance; }
  return (u - ramp / 2) / distance;
}
function fadeWindow(t, a, b, edge = 0.9) { return smooth((t - a) / edge) * (1 - smooth((t - b) / edge)); }
const chapters = [1, 2, 3].map(n => document.querySelector(`#chapter-${n}`));
const closing = document.querySelector('.closing');
const chapterWindows = [[0, 6.45], [7.4, 12.5], [13.5, 16.3]];
const cameraPoses = [
  [2.65, 5.65, 13.35],
  [-0.85, 4.75, 12.70],
  [0.85, 4.90, 12.05],
  [3.20, 4.70, 12.45],
  [1.45, 5.45, 13.30],
];
const cameraTargets = [[0.36, 2.48, 0], [0.10, 2.20, -0.15], [0.40, 2.17, 0], [0.85, 2.18, 0.15], [0.36, 2.48, 0]];
const path = points => new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p)), false, 'catmullrom', 0.30);
const cameraPath = path(cameraPoses);
const targetPath = path(cameraTargets);
const laptopMotion = path([[-0.11, 0, 0], [0.035, -0.13, 0], [-0.12, -0.17, -0.07], [-0.20, -0.08, -0.05], [-0.11, 0, 0]]);
const phoneMotion = path([[-0.10, 0, 0], [0.10, 0.08, -0.08], [-0.06, 0.02, 0.14], [0.12, -0.11, 0.20], [-0.10, 0, 0]]);
const laptopTimeline = [[0, 'dashboard-desktop'], [3.25, 'customers'], [7.0, 'invoice-builder'], [10.6, 'invoice-issued'], [15.0, 'invoice-paid']];
const phoneTimeline = [[0, 'dashboard-mobile-full'], [10.1, 'payment-mobile'], [13.65, 'payment-mobile-submit'], [15.0, 'payment-result-mobile']];
function contentAt(t, timeline) {
  let previous = timeline[0][1];
  for (let i = 1; i < timeline.length; i++) {
    const [start, name] = timeline[i];
    if (t < start) return { previous, current: previous, blend: 0 };
    const blend = smooth((t - start) / 1.0);
    if (blend < 1 || i === timeline.length - 1) return { previous, current: name, blend };
    previous = name;
  }
  return { previous, current: previous, blend: 0 };
}
function paintCapture(ctx, name, width, height, scroll = 0) {
  const source = captures[name];
  const nativeWidth = width === 1440 ? 1440 : 390;
  const nativeHeight = width === 1440 ? 900 : 844;
  ctx.drawImage(source, 0, scroll, nativeWidth, nativeHeight, 0, 0, width, height);
}
function pulse(ctx, name, marker, t, start, duration, scale = 1) {
  const rect = captureEvidence.captures[name]?.markers?.[marker];
  if (!rect || t < start || t > start + duration) return;
  const phase = (t - start) / duration;
  const x = (rect.x + rect.width / 2) * scale;
  const y = (rect.y + rect.height / 2) * scale;
  if (x < 30 || y < 30 || x > ctx.canvas.width - 30 || y > ctx.canvas.height - 30) return;
  ctx.save();
  ctx.globalAlpha = Math.sin(Math.PI * phase) * 0.80;
  ctx.strokeStyle = '#7d56d8'; ctx.lineWidth = 3 * scale;
  ctx.beginPath(); ctx.arc(x, y, (13 + 12 * phase) * scale, 0, 2 * Math.PI); ctx.stroke();
  ctx.fillStyle = '#ccf47f'; ctx.globalAlpha *= 0.4;
  ctx.beginPath(); ctx.arc(x, y, 7 * scale, 0, 2 * Math.PI); ctx.fill();
  ctx.restore();
}
function screenProjection(mesh, w, h) {
  const point = (x, y) => {
    const p = mesh.localToWorld(new THREE.Vector3(x, y, 0)).project(camera);
    return [345 + (p.x + 1) * W / 2, 130 + (1 - p.y) * H / 2];
  };
  return { center: point(0, 0), corners: [point(-w / 2, -h / 2), point(w / 2, -h / 2), point(w / 2, h / 2), point(-w / 2, h / 2)] };
}
function bodyProjection(parts) {
  const points = [];
  for (const [mesh, w, h, d] of parts) for (const x of [-w / 2, w / 2]) for (const y of [-h / 2, h / 2]) for (const z of [-d / 2, d / 2]) {
    const p = mesh.localToWorld(new THREE.Vector3(x, y, z)).project(camera);
    points.push([345 + (p.x + 1) * W / 2, 130 + (1 - p.y) * H / 2]);
  }
  return [Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1])), Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))];
}

window.renderFrame = function renderFrame(t) {
  t = Math.max(0, Math.min(DURATION, t));
  const travel = paced(t, 0, DURATION, 1.5);
  // Connected camera angles with continuous tangents, rather than hard cuts.
  camera.position.copy(cameraPath.getPoint(travel));
  camera.lookAt(targetPath.getPoint(travel));
  camera.fov = 33 - 1.1 * Math.sin(Math.PI * travel);
  camera.updateProjectionMatrix();
  const lm = laptopMotion.getPoint(travel);
  const pm = phoneMotion.getPoint(travel);
  laptop.rotation.y = lm.x;
  laptop.position.set(-0.83 + lm.y, 0.09, -0.25 + lm.z);
  phone.rotation.y = pm.x;
  phone.position.set(4.05 + pm.y, 0.17, 0.78 + pm.z);
  const desktopScroll = 0;
  const notebookContent = contentAt(t, laptopTimeline);
  const mobileContent = contentAt(t, phoneTimeline);
  const blend = notebookContent.blend;
  laptopCtx.globalAlpha = 1;
  laptopCtx.fillStyle = '#f7f7fb'; laptopCtx.fillRect(0, 0, 1440, 900);
  paintCapture(laptopCtx, notebookContent.previous, 1440, 900);
  laptopCtx.globalAlpha = blend;
  paintCapture(laptopCtx, notebookContent.current, 1440, 900);
  laptopCtx.globalAlpha = 1;
  pulse(laptopCtx, 'invoice-builder', 'product', t, 8.7, 1.3);
  laptopTexture.needsUpdate = true;
  const mobileScroll = 400 * paced(t, 0.8, 9.8, 1.5);
  phoneCtx.clearRect(0, 0, 780, 1688);
  phoneCtx.globalAlpha = 1;
  paintCapture(phoneCtx, mobileContent.previous, 780, 1688, mobileContent.previous === 'dashboard-mobile-full' ? mobileScroll : 0);
  phoneCtx.globalAlpha = mobileContent.blend;
  paintCapture(phoneCtx, mobileContent.current, 780, 1688, mobileContent.current === 'dashboard-mobile-full' ? mobileScroll : 0);
  phoneCtx.globalAlpha = 1;
  pulse(phoneCtx, 'payment-mobile', 'amount', t, 11.6, 1.25, 2);
  pulse(phoneCtx, 'payment-mobile-submit', 'submit', t, 14.4, 0.75, 2);
  phoneTexture.needsUpdate = true;
  chapters.forEach((el, i) => { el.style.opacity = String(fadeWindow(t, ...chapterWindows[i])); el.style.transform = `translateY(${5 * (1 - Number(el.style.opacity))}px)`; });
  closing.style.opacity = String(smooth((t - 17.1) / 1.1));
  renderer.render(scene, camera);
  return { time: t, mobileScroll, desktopScroll, blend, camera: camera.position.toArray(), cameraTarget: targetPath.getPoint(travel).toArray(), devices: { laptop: { position: laptop.position.toArray(), yaw: laptop.rotation.y }, phone: { position: phone.position.toArray(), yaw: phone.rotation.y } }, content: { laptop: notebookContent, phone: mobileContent }, webgl: !renderer.getContext().isContextLost(), bodies: { laptop: bodyProjection([[base, 6.85, 4.45, 0.22], [lidBack, 6.75, 4.35, 0.20]]), phone: bodyProjection([[phoneBody, 2.75, 5.86, 0.28]]) }, screens: { laptop: screenProjection(laptopDisplay, 6.18, 3.8625), phone: screenProjection(phoneDisplay, 2.45, 5.30205) } };
};
await document.fonts.ready;
window.renderFrame(0);
// The devices rotate and change position: their shadows must move with them.
renderer.shadowMap.autoUpdate = true;
window.videoReady = true;
window.videoMeta = { duration: DURATION, resolution: [1920, 1080], fps: 60, threeVersion: THREE.REVISION, pageSources: captureNames, cameraPoses, syntheticOperations: captureEvidence.operations };
window.prepareCapture = async function prepareCapture(plateData) {
  const plate = await image(plateData);
  const composite = Object.assign(document.createElement('canvas'), { width: 1920, height: 1080 });
  const ctx = composite.getContext('2d', { alpha: false });
  const labels = ['Clientes y catálogo.', 'Creá tus comprobantes.', 'Registrá pagos y saldos.'];
  window.captureFrame = t => {
    const state = window.renderFrame(t);
    ctx.globalAlpha = 1;
    ctx.drawImage(plate, 0, 0);
    ctx.drawImage(renderer.domElement, 345, 130);
    ctx.textBaseline = 'middle';
    chapters.forEach((el, i) => {
      ctx.globalAlpha = Number(el.style.opacity);
      const y = 894 + 5 * (1 - Number(el.style.opacity));
      ctx.strokeStyle = '#b9abce'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(129, y, 17, 0, 2 * Math.PI); ctx.stroke();
      ctx.fillStyle = '#504661'; ctx.font = '12px Studio'; ctx.textAlign = 'center';
      ctx.fillText(`0${i + 1}`, 129, y);
      ctx.font = '19px Studio'; ctx.textAlign = 'left'; ctx.fillText(labels[i], 159, y);
    });
    ctx.globalAlpha = Number(closing.style.opacity);
    ctx.fillStyle = '#504661'; ctx.textAlign = 'left'; ctx.font = '19px Studio';
    ctx.fillText('Menos complejidad. ', 112, 747);
    const closingWidth = ctx.measureText('Menos complejidad. ').width;
    ctx.font = '640 19px Studio'; ctx.fillText('Más claridad.', 112 + closingWidth, 747);
    ctx.globalAlpha = 1;
    return { state, jpeg: composite.toDataURL('image/jpeg', 0.97).split(',')[1] };
  };
};
if (new URLSearchParams(location.search).has('play')) {
  const start = performance.now();
  function animate(now) { window.renderFrame(Math.min(DURATION, (now - start) / 1000)); if (now - start < DURATION * 1000) requestAnimationFrame(animate); }
  requestAnimationFrame(animate);
}
