"""Create and verify a runtime-only Chrome Web Store ZIP."""
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
destination = ROOT / 'dist'
destination.mkdir(exist_ok=True)
package = destination / f'separate-window-{manifest["version"]}.zip'
files = [ROOT / name for name in ('manifest.json','background.js','content.js','media.js','popup.html','popup.css','popup.js')]
files += [ROOT / path for path in sorted(set(manifest['icons'].values()))]
files += sorted((ROOT / '_locales').glob('*/messages.json'))
with zipfile.ZipFile(package, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(ROOT).as_posix())
with zipfile.ZipFile(package) as archive:
    assert archive.testzip() is None
    names = set(archive.namelist())
    for path in manifest['icons'].values():
        assert path in names, path
    assert not any(name.startswith(('tests/','tools/','docs/','.git/')) for name in names)
    assert len(manifest['description']) <= 132
    for locale in ('ru','en'):
        messages = json.loads(archive.read(f'_locales/{locale}/messages.json'))
        assert len(messages['extensionDescription']['message']) <= 132
print(f'Verified {package.name}: {len(files)} runtime files, {package.stat().st_size} bytes')
materials = destination / f'chrome-web-store-materials-{manifest["version"]}.zip'
with zipfile.ZipFile(materials, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((ROOT / 'docs/store').rglob('*')):
        if path.is_file():
            archive.write(path, path.relative_to(ROOT / 'docs/store').as_posix())
    archive.write(ROOT / 'docs/privacy.html', 'privacy.html')
    archive.write(ROOT / 'icons/favicon.ico', 'favicon.ico')
print(f'Created {materials.name}: {materials.stat().st_size} bytes')
