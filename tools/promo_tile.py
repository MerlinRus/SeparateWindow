"""Export the approved generated master to the exact CWS small-tile format."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/.deps'))
import imageio_ffmpeg
from PIL import Image

source = ROOT / 'docs/store/source/search-tile-master.png'
destination = ROOT / 'docs/store/assets/promo-440x280.png'
subprocess.run([
    imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-v', 'error', '-i', str(source),
    '-vf', 'scale=440:280:force_original_aspect_ratio=increase:flags=lanczos,crop=440:280,format=rgb24',
    '-frames:v', '1', str(destination),
], check=True)
with Image.open(destination) as image:
    assert image.size == (440, 280) and image.mode == 'RGB'
print('PASS: CWS small promo tile, 440x280, RGB PNG without alpha')

# Review at half size, as recommended by the Chrome Web Store guidance.
preview = ROOT / 'tools/.artifacts/search-tile-220x140.png'
preview.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([
    imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-v', 'error', '-i', str(destination),
    '-vf', 'scale=220:140:flags=lanczos', '-frames:v', '1', str(preview),
], check=True)
