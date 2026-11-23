"""Validate CWS assets, localization, icons and the extracted release ZIP in Chromium."""
import json
from pathlib import Path
import re
import tempfile
import zipfile
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
assert manifest['manifest_version'] == 3 and manifest['default_locale'] == 'ru'
assert 'activeTab' not in manifest['permissions']
locales = {lang: json.loads((ROOT/f'_locales/{lang}/messages.json').read_text(encoding='utf-8')) for lang in ('ru','en')}
assert locales['ru'].keys() == locales['en'].keys()
for path in ('content.js','background.js','popup.html','welcome.html','invitation.js','manifest.json'):
    text = (ROOT / path).read_text(encoding='utf-8')
    keys = re.findall(r"\bt\('([^']+)'", text) + re.findall(r'__MSG_([^_]+)__',text) + re.findall(r'data-(?:i18n(?:-label)?|onboarding-copy)="([^"]+)"',text)
    for key in keys:
        assert key in locales['ru'], (path,key)
for lang, messages in locales.items():
    assert len(messages['extensionDescription']['message']) <= 132
    assert all(item['message'] for item in messages.values())
for size, path in manifest['icons'].items():
    with Image.open(ROOT / path) as image:
        assert image.size == (int(size),int(size)) and image.mode == 'RGBA'
        assert image.getpixel((0,0))[3] == 0
        if size != '128':
            bounds = image.getchannel('A').point(lambda alpha: 255 if alpha >= 128 else 0).getbbox()
            assert bounds == (0, 0, int(size), int(size)), path
assets = ROOT / 'docs/store/assets'
for path in assets.glob('screenshot-*.png'):
    with Image.open(path) as image:
        assert image.size == (1280,800) and image.mode == 'RGB', path
assert len(list(assets.glob('screenshot-*.png'))) == 8
global_screenshots = sorted(assets.glob('global-*.png'))
assert len(global_screenshots) == 4
for path in global_screenshots:
    with Image.open(path) as image:
        assert image.size == (1280,800) and image.mode == 'RGB', path
for size in ((440,280),(1400,560)):
    with Image.open(assets/f'promo-{size[0]}x{size[1]}.png') as image:
        assert image.size == size and image.mode == 'RGB'
with Image.open(ROOT/'icons/favicon.ico') as image:
    assert {(size, size) for size in (16, 24, 32, 48, 64, 128, 256)} == image.ico.sizes()
    for size in image.ico.sizes():
        alpha = image.ico.getimage(size).getchannel('A')
        assert alpha.point(lambda value: 255 if value >= 128 else 0).getbbox() == (0, 0, *size)
assert (ROOT/'icons/favicon.ico').read_bytes() == (ROOT/'docs/favicon.ico').read_bytes()
package = ROOT/f'dist/separate-window-{manifest["version"]}.zip'
with tempfile.TemporaryDirectory(prefix='sw-package-') as temp, zipfile.ZipFile(package) as archive:
    assert archive.testzip() is None
    for path in [*manifest['action']['default_icon'].values(), 'icons/favicon.ico', 'welcome.html', 'invitation.js']:
        assert path in archive.namelist(), path
    extracted = Path(temp)/'extension'
    archive.extractall(extracted)
    assert 'tests/smoke.py' not in archive.namelist()
    with sync_playwright() as p:
        for language in ('ru','en'):
            context = p.chromium.launch_persistent_context(str(Path(temp)/language), channel='chromium', headless=True,
                locale=f'{language}-'+('RU' if language=='ru' else 'US'),
                args=[f'--lang={language}',f'--disable-extensions-except={extracted}',f'--load-extension={extracted}'])
            try:
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                extension_id=worker.url.split('/')[2]
                page=context.pages[0]
                page.goto(f'chrome-extension://{extension_id}/popup.html')
                page.locator('#version').wait_for()
                assert page.locator('#version').text_content() == manifest['version']
                assert page.locator('#select').text_content().strip().endswith(locales[language]['selectButton']['message'])
                invite = page.locator('#onboarding-invite[open]')
                invite.get_by_role('button', name=locales[language]['onboardingSkip']['message']).wait_for()
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                assert page.locator('header img').evaluate('(e)=>e.complete&&e.naturalWidth>0')
                print(f'PASS: extracted CWS package loads with {language} UI and icon', flush=True)
            finally:
                context.close()
with zipfile.ZipFile(ROOT/f'dist/chrome-web-store-materials-{manifest["version"]}.zip') as archive:
    assert archive.testzip() is None
    assert 'privacy.html' in archive.namelist() and 'listing-ru.md' in archive.namelist()
print('PASS: locales, permissions, PNG dimensions/formats, favicon, runtime ZIP and materials ZIP')
