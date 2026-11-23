"""Check popup layout, external destinations and full-size toolbar icons."""
import json
from pathlib import Path
import tempfile
from urllib.parse import urlparse, parse_qs
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
    for size, filename in manifest['action']['default_icon'].items():
        with Image.open(ROOT/filename) as image, Image.open(ROOT/f'icons/icon{size}.png') as store:
            assert image.size==(int(size),int(size)) and image.mode=='RGBA'
            def width(im):
                bounds=im.getchannel('A').point(lambda alpha:255 if alpha>=128 else 0).getbbox()
                return bounds[2]-bounds[0]
            assert width(image)>=width(store)*1.25
    with tempfile.TemporaryDirectory(prefix='sw-popup-') as profile,sync_playwright() as p:
        context=p.chromium.launch_persistent_context(profile,channel='chromium',headless=True,
            args=[f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'])
        try:
            worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            page=context.new_page()
            page.set_viewport_size({'width':376,'height':600})
            page.goto(f'chrome-extension://{worker.url.split("/")[2]}/popup.html')
            page.locator('#version').wait_for()
            shortcut = worker.evaluate("async()=> (await chrome.commands.getAll()).find(c=>c.name==='select')?.shortcut || ''")
            for lang in ('ru','en'):
                page.locator(f'[data-language="{lang}"]').click()
                page.wait_for_function('(lang)=>document.documentElement.lang===lang',arg=lang)
                page.wait_for_function('![...document.querySelectorAll("[data-language]")].some(b=>b.disabled)')
                assert page.locator('#status').inner_text()==''
                messages = json.loads((ROOT/f'_locales/{lang}/messages.json').read_text(encoding='utf-8'))
                expected = shortcut or messages['shortcutUnassigned']['message']
                page.wait_for_function('value=>document.querySelector("#shortcut-keys").textContent===value', arg=expected)
                title = page.locator('.app-header h1 a').bounding_box()
                languages = page.get_by_role('group', name=messages['languageLabel']['message'], exact=True).bounding_box()
                version = page.locator('#version').bounding_box()
                assert title['x'] + title['width'] < languages['x'] and languages['x'] + languages['width'] < version['x']
                centers = [box['y'] + box['height'] / 2 for box in (title, languages, version)]
                assert max(centers) - min(centers) <= 2, centers
                assert page.get_by_text(messages['languageLabel']['message'], exact=True).count() == 0
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                height=page.locator('body').bounding_box()['height']
                assert height<=600, f'{lang} popup exceeds Chrome height: {height}'
                assert page.locator('footer nav a').first.get_attribute('id')=='rate'
                assert page.locator('#rate').get_attribute('href')==manifest['homepage_url']+'/reviews'
                for selector in ('#report-bug','#suggest-feature'):
                    link=page.locator(selector)
                    url=urlparse(link.get_attribute('href'))
                    assert url.netloc=='github.com' and url.path=='/MerlinRus/SeparateWindow/issues/new'
                    query=parse_qs(url.query)
                    assert manifest['version'] in query['body'][0]
                    assert query['title'][0].startswith(('Баг:' if selector=='#report-bug' else 'Идея:') if lang=='ru' else ('Bug:' if selector=='#report-bug' else 'Idea:'))
                    assert 'http' not in query['body'][0], 'Do not attach the active page URL automatically'
                    assert link.get_attribute('rel')=='noopener noreferrer'
                assert page.locator('.feedback a[href^="mailto:"]').get_attribute('href')=='mailto:qobuz43@gmail.com'
                page.screenshot(path=str(ROOT/f'tests/popup-{lang}.png'),full_page=True)
                print(f'PASS: {lang} popup {height}px, inline language switch, rating, localized issue drafts and email')
        finally:context.close()
    print('PASS: toolbar mark is at least 25% larger; padded store icon preserved')


if __name__=='__main__':main()
