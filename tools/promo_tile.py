"""Export the generated English masters to both exact CWS promo formats."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/.deps'))
import imageio_ffmpeg
from PIL import Image

for master, width, height in [('search-tile-master.png', 440, 280), ('marquee-master.png', 1400, 560)]:
    source = ROOT / 'docs/store/source' / master
    destination = ROOT / f'docs/store/assets/promo-{width}x{height}.png'
    subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-v', 'error', '-i', str(source),
        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,crop={width}:{height},format=rgb24',
        '-frames:v', '1', str(destination),
    ], check=True)
    with Image.open(destination) as image:
        assert image.size == (width, height) and image.mode == 'RGB'
    print(f'PASS: CWS promo {width}x{height}, RGB PNG without alpha')

# Review at half size, as recommended by the Chrome Web Store guidance.
preview = ROOT / 'tools/.artifacts/search-tile-220x140.png'
preview.parent.mkdir(parents=True, exist_ok=True)
subprocess.run([
    imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-v', 'error', '-i', str(ROOT / 'docs/store/assets/promo-440x280.png'),
    '-vf', 'scale=220:140:flags=lanczos', '-frames:v', '1', str(preview),
], check=True)
