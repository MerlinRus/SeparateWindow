"""Build the static Russian and English landing pages and tutorial."""

import json
import re
import tarfile
from hashlib import sha256
from html import escape
from pathlib import Path
from shutil import copyfile
from string import Template
from urllib.parse import urlencode

from PIL import Image


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent
OUTPUT = ROOT / 'dist' / 'website'
HOST = 'https://separate.maark.ru'
STORE = 'https://chromewebstore.google.com/detail/separate-window/fhcafcdfknddjfgbbkhpglgamceiclcm'
ISSUES = 'https://github.com/MerlinRus/SeparateWindow/issues/new'
ROUTES = {'ru': '/', 'en': '/en/'}


def write(path, content):
    target = OUTPUT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8', newline='\n')


def main():
    template = Template((SOURCE / 'index.html').read_text(encoding='utf-8'))
    copy = json.loads((SOURCE / 'copy.json').read_text(encoding='utf-8'))
    tour = Template((SOURCE / 'onboarding.html').read_text(encoding='utf-8'))
    tour_copy = json.loads((SOURCE / 'onboarding-copy.json').read_text(encoding='utf-8'))
    style_version = sha256((SOURCE / 'site.css').read_bytes()).hexdigest()[:12]
    script_version = sha256((SOURCE / 'site.js').read_bytes()).hexdigest()[:12]
    tour_style_version = sha256((SOURCE / 'onboarding.css').read_bytes()).hexdigest()[:12]
    tour_script_version = sha256((SOURCE / 'onboarding.js').read_bytes()).hexdigest()[:12]
    for lang, path in ROUTES.items():
        variables = {key: escape(value, quote=True) for key, value in copy[lang].items()}
        messages = json.loads((ROOT / '_locales' / lang / 'messages.json').read_text(encoding='utf-8'))
        for kind in ('bug', 'feature'):
            query = urlencode({
                'title': messages[f'{kind}Title']['message'],
                'body': messages[f'{kind}Body']['message'].replace('$1', '…'),
            })
            variables[f'{kind}_url'] = escape(f'{ISSUES}?{query}', quote=True)
        current = ' aria-current="page"'
        page = template.substitute(
            **variables, lang=lang, home=path, canonical=HOST + path, store=STORE,
            style_version=style_version, script_version=script_version,
            current_ru=current if lang == 'ru' else '',
            current_en=current if lang == 'en' else '',
        )
        write(path.lstrip('/') + 'index.html', page)
        lesson = tour.substitute(
            {key: escape(value, quote=True) for key, value in tour_copy[lang].items()},
            lang=lang, home=path, store=STORE, style_version=style_version,
            tour_style_version=tour_style_version, tour_script_version=tour_script_version,
            current_ru=current if lang == 'ru' else '', current_en=current if lang == 'en' else '',
        )
        write(path.lstrip('/') + 'onboarding/index.html', lesson)
    missing = Template((SOURCE / '404.html').read_text(encoding='utf-8'))
    write('404.html', missing.substitute(style_version=style_version))
    write('robots.txt', f'User-agent: *\nAllow: /\nSitemap: {HOST}/sitemap.xml\n')
    urls = '\n'.join(f'  <url><loc>{HOST}{path}</loc></url>' for path in ROUTES.values())
    write('sitemap.xml', f'<?xml version="1.0" encoding="UTF-8"?>\n'
                         f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n')

    privacy = (ROOT / 'docs' / 'privacy.html').read_text(encoding='utf-8')
    style = re.search(r'<style>(.*?)</style>', privacy, flags=re.DOTALL)
    privacy_css = style.group(1).strip() + '\n'
    write('assets/privacy.css', privacy_css)
    privacy_version = sha256(privacy_css.encode('utf-8')).hexdigest()[:12]
    privacy = privacy.replace(style.group(), f'<link rel="stylesheet" href="/assets/privacy.css?v={privacy_version}">')
    privacy = privacy.replace('src="store/assets/icon128.png"', 'src="/assets/icon.png"')
    privacy = privacy.replace('<body><main>', '<body><main><p><a href="/">Separate Window</a></p>')
    write('privacy.html', privacy)

    assets = OUTPUT / 'assets'
    store_assets = ROOT / 'docs' / 'store' / 'assets'
    promo = store_assets / 'promo-1400x560.png'
    copyfile(ROOT / 'icons' / 'favicon.ico', OUTPUT / 'favicon.ico')
    copyfile(ROOT / 'icons' / 'icon128.png', assets / 'icon.png')
    copyfile(promo, assets / 'share.png')
    for filename in ('site.css', 'site.js', 'onboarding.css', 'onboarding.js', 'onboarding-loop.mp4'):
        copyfile(SOURCE / filename, assets / filename)
    with Image.open(promo) as artwork:
        artwork.crop((880, 180, 1336, 437)).convert('RGB').save(assets / 'landscape.webp', quality=88)

    bundle = OUTPUT.with_name('separate-window-website.tar.gz')
    with tarfile.open(bundle, 'w:gz') as archive:
        archive.add(OUTPUT, arcname='public')
        for config in sorted(SOURCE.glob('nginx-*.conf')):
            archive.add(config, arcname=config.name)
    print(f'Built {bundle.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
