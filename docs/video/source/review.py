"""Revisa el MP4 decodificado y extrae fotogramas para inspección visual."""
from pathlib import Path
import hashlib
import json
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
VIDEO = ROOT / 'fracxion-comercial-3d-dinamico.mp4'
probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(VIDEO)]))
video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
assert (video['width'], video['height']) == (1920, 1080)
assert video['avg_frame_rate'] == '60/1'
assert video['nb_read_frames'] == '1140'
assert video['codec_name'] == 'h264' and video['pix_fmt'] == 'yuv420p'
assert abs(float(video['duration']) - 19) < 0.01
assert float(probe['format']['duration']) <= 20
assert audio['codec_name'] == 'aac' and audio['channels'] == 2
subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(VIDEO), '-f', 'null', '-'], check=True)

# Decode every frame, detect identical consecutive frames and abrupt changes.
process = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', str(VIDEO), '-vf', 'scale=320:180', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], stdout=subprocess.PIPE)
previous = None
differences = []
freeze = 0
max_freeze = 0
frame_count = 0
while True:
    raw = process.stdout.read(320 * 180)
    if not raw:
        break
    assert len(raw) == 320 * 180
    frame = np.frombuffer(raw, np.uint8).astype(np.float32)
    if previous is not None:
        difference = float(np.mean(np.abs(frame - previous)))
        differences.append(difference)
        freeze = freeze + 1 if difference < 0.001 else 0
        max_freeze = max(max_freeze, freeze)
    previous = frame
    frame_count += 1
assert process.wait() == 0 and frame_count == 1140
assert max_freeze <= 2, f'Fotogramas congelados consecutivos: {max_freeze}'
diff = np.asarray(differences)
assert float(diff.max()) < 3.0, f'Salto brusco entre fotogramas: {diff.max()}'

raw_audio = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(VIDEO), '-vn', '-f', 'f32le', '-acodec', 'pcm_f32le', '-'])
samples = np.frombuffer(raw_audio, '<f4')
assert np.isfinite(samples).all()
assert float(np.max(np.abs(samples))) < 0.95

diagnostics = json.loads((ROOT / 'render-diagnostics.json').read_text())
assert diagnostics['errors'] == []
assert all(row['webgl'] for row in diagnostics['diagnostics'])
assert len(diagnostics['diagnostics']) == 1140
times = np.array([row['time'] for row in diagnostics['diagnostics']])
assert np.allclose(np.diff(times), 1 / 60)
scroll = np.array([row['mobileScroll'] for row in diagnostics['diagnostics']])
assert np.all(np.diff(scroll) >= -1e-6)
assert np.max(np.diff(scroll)) < 1.2  # At most 72 CSS px per second.
camera = np.array([row['camera'] for row in diagnostics['diagnostics']])
camera_steps = np.linalg.norm(np.diff(camera, axis=0), axis=1)
assert np.max(camera_steps) < 0.05
assert np.ptp(camera[:, 0]) > 3, 'Los cambios de ángulo deben ser visibles.'
for device in ['laptop', 'phone']:
    yaw = np.array([row['devices'][device]['yaw'] for row in diagnostics['diagnostics']])
    assert np.ptp(yaw) > 0.15
    assert np.max(np.abs(np.diff(yaw))) < 0.01
assert {row['content']['laptop']['current'] for row in diagnostics['diagnostics']} >= {'customers', 'invoice-builder', 'invoice-issued', 'invoice-paid'}
assert {row['content']['phone']['current'] for row in diagnostics['diagnostics']} >= {'payment-mobile', 'payment-mobile-submit', 'payment-result-mobile'}
for row in diagnostics['diagnostics']:
    for screen in row['screens'].values():
        assert all(550 < x < 1850 and 180 < y < 970 for x, y in screen['corners'])
    for body in row['bodies'].values():
        left, top, right, bottom = body
        assert 375 < left < right < 1890 and 150 < top < bottom < 995, f'Dispositivo recortado: {row["time"]} {body}'

review_dir = ROOT / 'review'
review_dir.mkdir(exist_ok=True)
sample_times = [0, 2.5, 5.5, 8.5, 11.5, 14.4, 16.5, 18.9]
contact = Image.new('RGB', (1600, 1900), '#e9e4f1')
draw = ImageDraw.Draw(contact)
font = ImageFont.truetype(str(ROOT / 'source/vendor/AdwaitaSans.ttf'), 23)
for index, time in enumerate(sample_times):
    target = review_dir / f'frame-{index:02d}.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(time), '-i', str(VIDEO), '-frames:v', '1', '-update', '1', str(target)], check=True)
    image = Image.open(target).convert('RGB')
    frame_diagnostics = diagnostics['diagnostics'][min(1139, round(time * 60))]
    for screen in frame_diagnostics['screens'].values():
        x, y = (round(v) for v in screen['center'])
        # A failed or occluded display was almost black in the first preview.
        luminance = np.array(image.crop((x - 15, y - 15, x + 15, y + 15))).mean()
        assert luminance > 150, f'Pantalla negra o tapada a {time} s: {luminance}'
    image.thumbnail((780, 439), Image.Resampling.LANCZOS)
    x = (index % 2) * 800 + 10
    y = (index // 2) * 475 + 8
    contact.paste(image, (x, y))
    draw.text((x, y + 443), f'{time:04.1f} s', font=font, fill='#524565')
contact.save(ROOT / 'revision-fotogramas.jpg', quality=93)
poster = Image.open(review_dir / 'frame-01.png')
poster.save(ROOT / 'portada.jpg', quality=96)
report = {
    'duration_seconds': float(probe['format']['duration']),
    'resolution': [video['width'], video['height']],
    'fps': video['avg_frame_rate'],
    'frames_decoded': frame_count,
    'codecs': [video['codec_name'], audio['codec_name']],
    'max_consecutive_duplicate_frames': max_freeze,
    'mean_pixel_change': float(diff.mean()),
    'max_pixel_change': float(diff.max()),
    'max_mobile_scroll_px_per_second': float(np.max(np.diff(scroll)) * 60),
    'camera_horizontal_travel': float(np.ptp(camera[:, 0])),
    'max_camera_step': float(np.max(camera_steps)),
    'features': ['customers', 'invoice-builder', 'invoice-issued', 'payment-mobile', 'invoice-paid'],
    'max_audio_peak': float(np.max(np.abs(samples))),
    'browser_errors': diagnostics['errors'],
    'screens_visible_and_in_frame': 'passed',
    'full_decode': 'passed',
    'sha256': hashlib.sha256(VIDEO.read_bytes()).hexdigest(),
}
(ROOT / 'revision-tecnica.json').write_text(json.dumps(report, indent=2) + '\n')
(ROOT / 'SHA256SUMS.txt').write_text(f"{report['sha256']}  {VIDEO.name}\n")
print(json.dumps(report, indent=2))
