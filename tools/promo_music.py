"""Original, sample-free instrumental score for the Separate Window promo.

All instruments are synthesized from oscillators and seeded noise. No external
recordings, MIDI files, melodies or sample libraries are loaded.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'tools/.artifacts/promo'
sys.path.insert(0, str(ROOT / 'tools/.deps'))
import imageio_ffmpeg
import numpy as np

RATE = 48000
BPM = 100
BEAT = 60 / BPM


def frequency(note):
    return 440 * 2 ** ((note - 69) / 12)


def compose(duration):
    """Soft electric keys, warm bass, brushed percussion and stereo echoes."""
    mix = np.zeros((round(duration * RATE), 2), dtype=np.float64)
    rng = np.random.default_rng(7112026)

    def place(sound, at, level, pan=0):
        start = round(at * RATE)
        count = min(len(sound), len(mix) - start)
        if count <= 0:
            return
        angle = (pan + 1) * np.pi / 4
        mix[start:start + count, 0] += sound[:count] * level * np.cos(angle)
        mix[start:start + count, 1] += sound[:count] * level * np.sin(angle)

    def key(note, length, bright=0.7):
        t = np.arange(round(length * RATE)) / RATE
        phase = 2 * np.pi * frequency(note) * t
        tone = np.sin(phase + bright * np.exp(-t * 6) * np.sin(phase * 2))
        tone += .12 * np.sin(phase * 3) * np.exp(-t * 9)
        envelope = (1 - np.exp(-t * 260)) * np.exp(-t * 2.7)
        envelope *= np.minimum(1, (length - t) / .08)
        return tone * envelope

    # Ten bars, with a resolved final D voicing. Notes are written for this film.
    chords = [
        (38, [62, 66, 69, 73, 76]), (35, [62, 66, 69, 71, 74]),
        (31, [59, 62, 66, 69, 74]), (33, [61, 64, 69, 71, 76]),
        (38, [62, 66, 69, 73, 76]), (35, [62, 66, 69, 71, 74]),
        (31, [59, 62, 66, 69, 74]), (33, [61, 64, 69, 71, 76]),
        (31, [59, 62, 66, 69, 74]), (38, [62, 66, 69, 73, 76]),
    ]
    melody = [
        [(0.5, 78), (2, 76), (3.5, 73)], [(1, 74), (2.5, 78)],
        [(0.5, 78), (2.5, 81), (3.5, 78)], [(1, 76), (3, 73)],
        [(0.5, 78), (2, 81)], [(1.5, 78), (3, 74)],
        [(0.5, 74), (2, 78), (3.5, 81)], [(1, 76), (3, 73)],
        [(0.5, 74), (2, 78)], [(0, 78), (1.5, 76), (2.5, 74)],
    ]
    for bar, (root, notes) in enumerate(chords):
        at = bar * 4 * BEAT
        # Sustained pad: a quiet bed under the shorter electric piano notes.
        length = 4 * BEAT + .5
        t = np.arange(round(length * RATE)) / RATE
        envelope = np.minimum(t / .3, 1) * np.minimum((length - t) / .65, 1)
        for i, note in enumerate(notes):
            phase = 2 * np.pi * frequency(note - 12) * t
            pad = (np.sin(phase) + .14 * np.sin(phase * 2)) * envelope
            place(pad, at, .012, (i - 2) / 3)
        for beat, strength in [(0, .07), (1.5, .045), (2.5, .055)]:
            for i, note in enumerate(notes[:-1]):
                place(key(note, 1.5), at + beat * BEAT + i * .014,
                      strength, (i - 1.5) / 3)
        for beat in [0, 1.5, 2.5]:
            t = np.arange(round(.52 * RATE)) / RATE
            bass = np.sin(2 * np.pi * frequency(root) * t)
            bass += .18 * np.sin(4 * np.pi * frequency(root) * t)
            bass *= (1 - np.exp(-t * 150)) * np.exp(-t * 5)
            bass *= np.minimum(1, (.52 - t) / .05)
            place(bass, at + beat * BEAT, .15)
        for beat, note in melody[bar]:
            sound = key(note, 1.4, .45)
            place(sound, at + beat * BEAT, .063, -.15)
            place(sound, at + (beat + .75) * BEAT, .019, .55)
            place(sound, at + (beat + 1.5) * BEAT, .008, -.55)
        # Leave the last bar without percussion for the closing brand card.
        if bar == 9:
            continue
        for beat in [0, 2]:
            t = np.arange(round(.3 * RATE)) / RATE
            phase = 2 * np.pi * (46 * t + 52 * .025 * (1 - np.exp(-t / .025)))
            kick = np.sin(phase) * np.exp(-t * 21) * (1 - np.exp(-t * 500))
            place(kick, at + beat * BEAT, .2)
        for beat in [1, 3]:
            t = np.arange(round(.12 * RATE)) / RATE
            noise = rng.standard_normal(len(t))
            brush = np.convolve(noise, np.ones(9) / 9, mode='same')
            brush *= np.exp(-t * 42) * (1 - np.exp(-t * 900))
            place(brush, at + beat * BEAT, .075, .1)
        for step in range(8):
            t = np.arange(round(.08 * RATE)) / RATE
            noise = rng.standard_normal(len(t))
            hat = noise - np.convolve(noise, np.ones(13) / 13, mode='same')
            hat *= np.exp(-t * 75) * (1 - np.exp(-t * 1500))
            place(hat, at + step * BEAT / 2, .016 if step % 2 else .01,
                  -.35 if step % 2 else .35)

    time = np.arange(len(mix)) / RATE
    fade = np.minimum(time / .6, 1) * np.minimum((duration - time) / 1.7, 1)
    mix *= fade[:, None]
    mix *= .7 / max(np.max(np.abs(mix)), .001)
    assert np.isfinite(mix).all()
    assert np.max(np.abs(mix)) < 1
    return (mix * 32767).astype('<i2')


def add_music(video, duration):
    ART.mkdir(parents=True, exist_ok=True)
    wav = ART / 'original-score.wav'
    audio = compose(duration)
    with wave.open(str(wav), 'wb') as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(audio.tobytes())
    output = video.with_stem(video.stem + '-music')
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-v', 'error',
        '-i', str(video), '-i', str(wav), '-map', '0:v:0', '-map', '1:a:0',
        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-ar', str(RATE),
        '-af', 'loudnorm=I=-20:TP=-2:LRA=7', '-t', str(duration),
        '-movflags', '+faststart', str(output),
    ], check=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-v', 'error',
                    '-i', str(output), '-f', 'null', '-'], check=True)
    provenance = {
        'title': 'Separate Window promo score',
        'source': 'tools/promo_music.py', 'bpm': BPM, 'sample_rate': RATE,
        'duration': duration, 'external_samples': False,
        'external_compositions': False, 'seed': 7112026,
        'pcm_sha256': hashlib.sha256(audio.tobytes()).hexdigest(),
        'wav_sha256': hashlib.sha256(wav.read_bytes()).hexdigest(),
        'notes': 'New instrumental score synthesized for this project. '
                 'No third-party attribution required. No Content ID registration '
                 'has been requested. YouTube matching has not been tested.',
    }
    (ART / 'music-provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print(f'PASS: original stereo score, AAC 48kHz, full MP4 decode: {output.name}', flush=True)
    return output


if __name__ == '__main__':
    version = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))['version']
    video = ROOT / f'dist/separate-window-global-promo-{version}.mp4'
    reader = imageio_ffmpeg.read_frames(str(video))
    metadata = next(reader)
    reader.close()
    add_music(video, metadata['duration'])
