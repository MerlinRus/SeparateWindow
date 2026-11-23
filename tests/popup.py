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
            card = page.locator('#auto-pip-option')
            assert card.is_hidden(), 'The switch is hidden on unsupported pages'
            # Show the supported-site layout without changing the active tab or permissions.
            card.evaluate('element => {element.hidden = false; element.querySelector("input").disabled = false;}')
            command = worker.evaluate("async()=> (await chrome.commands.getAll()).find(c=>c.name==='select')")
            shortcut = manifest['commands']['select']['suggested_key']['default']
            assert command['shortcut'] == shortcut
            for lang in ('ru','en'):
                page.locator(f'[data-language="{lang}"]').click()
                page.wait_for_function('(lang)=>document.documentElement.lang===lang',arg=lang)
                page.wait_for_function('![...document.querySelectorAll("[data-language]")].some(b=>b.disabled)')
                assert page.locator('#status').inner_text()==''
                messages = json.loads((ROOT/f'_locales/{lang}/messages.json').read_text(encoding='utf-8'))
                page.wait_for_function('value=>document.querySelector("#shortcut-keys").textContent===value', arg=shortcut)
                title = page.locator('.app-header h1 a').bounding_box()
                languages = page.get_by_role('group', name=messages['languageLabel']['message'], exact=True).bounding_box()
                version = page.locator('#version').bounding_box()
                assert title['x'] + title['width'] < languages['x'] and languages['x'] + languages['width'] < version['x']
                centers = [box['y'] + box['height'] / 2 for box in (title, languages, version)]
                assert max(centers) - min(centers) <= 2, centers
                logo = page.locator('.app-header img').bounding_box()
                tagline = page.locator('[data-i18n="appTagline"]').bounding_box()
                assert tagline['x'] == title['x'] and tagline['y'] + tagline['height'] <= logo['y'] + logo['height']
                assert page.get_by_text(messages['languageLabel']['message'], exact=True).count() == 0
                assert page.locator('#forget').count() == 0, 'The popup must not contain the old selection reset button'
                switch = page.get_by_role('switch', name=messages['autoPipLabel']['message'], exact=True)
                assert switch.is_visible() and switch.get_attribute('type') == 'checkbox'
                help_text = page.locator('#' + switch.get_attribute('aria-describedby'))
                assert help_text.is_visible() and help_text.text_content() == messages['autoPipHelp']['message']
                box = card.bounding_box()
                restore = page.locator('#restore').bounding_box()
                assert box['y'] + box['height'] < restore['y'] and box['width'] == restore['width']
                page.locator('#select').focus()
                page.keyboard.press('Tab')
                assert switch.evaluate('element => element.matches(":focus-visible")')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                height=page.locator('body').bounding_box()['height']
                assert height<=600, f'{lang} popup exceeds Chrome height: {height}'
                assert page.locator('footer nav a').first.get_attribute('id')=='rate'
                assert page.locator('#rate').get_attribute('href')==manifest['homepage_url']+'/reviews'
                share_button = page.get_by_role('button', name=messages['shareExtension']['message'], exact=True)
                assert share_button.is_visible()
                share_box = share_button.bounding_box()
                idea = page.locator('#suggest-feature').bounding_box()
                email = page.locator('.feedback a[href^="mailto:"]').bounding_box()
                assert share_box['x'] == idea['x'] and share_box['width'] == idea['width']
                assert share_box['y'] > idea['y'] + idea['height']
                assert abs(share_box['y'] + share_box['height'] / 2 - email['y'] - email['height'] / 2) <= 1
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

            # Capture Clipboard API calls without touching the desktop clipboard.
            page.evaluate('''() => {
              window.shareWrites = [];
              navigator.clipboard.writeText = async (text) => {
                if (window.denyClipboardWrite) throw new DOMException('Denied', 'NotAllowedError');
                window.shareWrites.push({text, activated:navigator.userActivation.isActive});
              };
            }''')
            share = page.locator('#share')
            share_status = page.locator('#share-status')
            share.click()
            page.wait_for_function('message => document.querySelector("#share-status").textContent === message',
                                   arg=messages['shareCopied']['message'])
            assert share_status.is_visible()
            assert page.evaluate('window.shareWrites') == [{'text': manifest['homepage_url'], 'activated': True}]
            page.locator('[data-language="ru"]').click()
            russian = json.loads((ROOT/'_locales/ru/messages.json').read_text(encoding='utf-8'))
            page.wait_for_function('message => document.querySelector("#share-status").textContent === message',
                                   arg=russian['shareCopied']['message'])
            page.evaluate('window.denyClipboardWrite = true')
            share.click()
            page.wait_for_function('message => document.querySelector("#share-status").textContent === message',
                                   arg=russian['shareCopyFailed']['message'])
            assert page.evaluate('window.shareWrites.length') == 1
            print('PASS: sharing writes the Chrome Web Store URL after a click and shows localized success and failure messages')

            settings_url = 'chrome://extensions/shortcuts'
            command_name = command['description']
            settings = context.new_page()
            settings.goto(settings_url)
            field = settings.locator('cr-shortcut-input').filter(has=settings.get_by_role('textbox', name=command_name))
            field.get_by_role('button').click()
            settings.keyboard.press('Backspace')
            settings.close()

            page.reload()
            for lang, label in (('ru', 'Назначить клавиши'), ('en', 'Assign shortcut')):
                page.locator(f'[data-language="{lang}"]').click()
                page.get_by_role('button', name=label, exact=True).wait_for(timeout=5000)
            with context.expect_page() as opened:
                page.get_by_role('button', name='Assign shortcut', exact=True).click()
            settings = opened.value
            settings.wait_for_url(settings_url)
            field = settings.locator('cr-shortcut-input').filter(has=settings.get_by_role('textbox', name=command_name))
            field.get_by_role('button').click()
            settings.keyboard.press(shortcut)
            settings.close()
            page.reload()
            page.wait_for_function('value=>document.querySelector("#shortcut-keys").textContent===value', arg=shortcut)
            assert page.locator('#shortcut-keys kbd').all_text_contents() == shortcut.split('+')
            print('PASS: clearing the shortcut shows a localized action that opens Chrome settings and supports restoring the shortcut')
        finally:context.close()
    print('PASS: toolbar mark is at least 25% larger; padded store icon preserved')


if __name__=='__main__':main()
