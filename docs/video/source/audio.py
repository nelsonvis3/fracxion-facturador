"""Banda instrumental original, serena, a 78 BPM; no utiliza muestras externas."""
from pathlib import Path
import wave

import numpy as np

RATE = 48000
DURATION = 19
OUT = Path('/tmp/fracxion-video-frames/soundtrack.wav')
OUT.parent.mkdir(parents=True, exist_ok=True)
t = np.arange(RATE * DURATION, dtype=np.float64) / RATE
stereo = np.zeros((len(t), 2), dtype=np.float64)
beat = 60 / 78


def note(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def envelope(local, length, attack, release):
    rise = np.sin(np.clip(local / attack, 0, 1) * np.pi / 2) ** 2
    fall = np.sin(np.clip((length - local) / release, 0, 1) * np.pi / 2) ** 2
    return rise * fall * ((local >= 0) & (local < length))


chords = [[50, 57, 61, 66, 69], [47, 54, 57, 62, 66], [43, 50, 57, 59, 62], [45, 52, 57, 62, 64], [50, 57, 61, 66, 69]]
for index, chord in enumerate(chords):
    start = index * beat * 4
    length = beat * 4 + 1.4
    local = t - start
    env = envelope(local, length, 0.95, 1.4)
    for position, midi in enumerate(chord):
        frequency = note(midi)
        pan = 0.18 + 0.64 * position / (len(chord) - 1)
        tone = (np.sin(2 * np.pi * frequency * local) + 0.16 * np.sin(2 * np.pi * frequency * 2 * local))
        tone *= 0.015 * env * (1 + 0.04 * np.sin(2 * np.pi * 0.18 * local))
        stereo[:, 0] += tone * np.sqrt(1 - pan)
        stereo[:, 1] += tone * np.sqrt(pan)
    # Widely spaced, soft electric-piano accents.
    for offset, pitch in enumerate([chord[2] + 12, chord[4] + 12, chord[3] + 12]):
        onset = start + beat * (offset + 0.5)
        local = t - onset
        env = envelope(local, 2.2, 0.065, 0.55) * np.exp(-np.maximum(local, 0) / 0.65)
        frequency = note(pitch)
        tone = 0.027 * env * (np.sin(2 * np.pi * frequency * local) + 0.1 * np.sin(2 * np.pi * frequency * 3 * local))
        stereo[:, 0] += tone * 0.76
        stereo[:, 1] += tone * 0.70
    bass = 0.023 * envelope(t - start, length, 0.5, 1.3) * np.sin(2 * np.pi * note(chord[0] - 12) * (t - start))
    stereo += bass[:, None]

fade = envelope(t, DURATION, 1.2, 2.25)
stereo *= fade[:, None]
stereo *= 0.24 / np.max(np.abs(stereo))
assert np.max(np.abs(stereo)) < 1
pcm = np.round(stereo * 32767).astype('<i2')
with wave.open(str(OUT), 'wb') as audio:
    audio.setnchannels(2)
    audio.setsampwidth(2)
    audio.setframerate(RATE)
    audio.writeframes(pcm.tobytes())
print(f'{OUT}: {DURATION} s, estéreo, {RATE} Hz, pico {np.max(np.abs(stereo)):.4f}')
