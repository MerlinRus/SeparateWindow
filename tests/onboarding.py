"""Check the first-run prompts and hosted exercises with a real Chromium extension."""
import json
import mimetypes
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / 'dist/website'
HOST = 'https://separate.maark.ru'
CSP = re.search(r'Content-Security-Policy "([^"]+)"', (ROOT / 'website/nginx-site.conf').read_text())[1]


def serve_site(route):
    path = (SITE / urlparse(route.request.url).path.lstrip('/')).resolve()
    assert path.is_relative_to(SITE)
    if path.is_dir():
        path /= 'index.html'
    if not path.is_file():
        route.fulfill(status=404, body='Not found')
        return
    headers = {'content-security-policy': CSP}
    content_type = mimetypes.guess_type(path)[0]
    if path.suffix in ('.html', '.js', '.css'):
        content_type += '; charset=utf-8'
    if path.suffix == '.mp4':
        data = path.read_bytes()
        headers['accept-ranges'] = 'bytes'
        first, last = map(lambda value: int(value) if value else None,
                          route.request.headers.get('range', 'bytes=0-')[6:].split('-', 1))
        last = min(last if last is not None else len(data) - 1, len(data) - 1)
        headers['content-range'] = f'bytes {first}-{last}/{len(data)}'
        route.fulfill(status=206, content_type=content_type, headers=headers, body=data[first:last + 1])
    else:
        route.fulfill(path=path, content_type=content_type, headers=headers)


def installed(context):
    worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
    base = worker.url.rsplit('/', 1)[0]
    welcome_url = base + '/welcome.html'
    welcome = next((page for page in context.pages if page.url == welcome_url), None)
    if welcome is None:
        welcome = context.wait_for_event('page', timeout=8000, predicate=lambda page: page.url in ('', welcome_url))
    welcome.wait_for_url(welcome_url)
    welcome.locator('[data-onboarding-choice=start]').wait_for()
    assert worker.evaluate("(async()=> (await chrome.storage.local.get('onboarding')).onboarding)()") == 'pending'
    return worker, base, welcome


def launch(playwright, profile):
    return playwright.chromium.launch_persistent_context(
        profile, channel='chromium', headless=True,
        args=[f'--disable-extensions-except={ROOT}', f'--load-extension={ROOT}', '--no-first-run'],
    )


def exercise(page, worker, context):
    page.set_default_timeout(8000)
    page.wait_for_selector('html[data-separate-window-tour="ready"]', state='attached')
    assert page.locator('#tour-install').is_hidden()
    assert page.locator('#tour-next').is_hidden()
    page.locator('#practice-video').evaluate('''async video => {
      await video.play();
      if (video.currentTime <= .1) await new Promise(resolve => video.addEventListener('timeupdate', resolve, {once:true}));
    }''')
    cdp = context.new_cdp_session(page)
    labels = worker.evaluate("Object.fromEntries(['returnTitle','zoomOut','pinTitle','unpinTitle'].map(key=>[key,t(key)]))")

    def click_toolbar(key):
        def find_button(node):
            attrs = dict(zip(node.get('attributes', [])[::2], node.get('attributes', [])[1::2]))
            if node['nodeName'] == 'BUTTON' and attrs.get('aria-label') == labels[key]:
                return node['nodeId']
            for child in node.get('children', []) + node.get('shadowRoots', []):
                if found := find_button(child):
                    return found
        tree = cdp.send('DOM.getDocument', {'depth': -1, 'pierce': True})['root']
        node = find_button(tree)
        assert node, key
        quad = cdp.send('DOM.getBoxModel', {'nodeId': node})['model']['border']
        x, y = (quad[0] + quad[4]) / 2, (quad[1] + quad[5]) / 2
        page.mouse.move(x, y)
        page.mouse.click(x, y)

    def detach(locator, x_offset=None):
        locator.scroll_into_view_if_needed()
        bounds = locator.bounding_box()
        page.mouse.move(bounds['x'] + (bounds['width'] / 2 if x_offset is None else x_offset),
                        bounds['y'] + bounds['height'] / 2)
        worker.evaluate("async url => {const [tab] = await chrome.tabs.query({url}); await toggleSelection(tab.id)}", page.url)
        page.mouse.click(bounds['x'] + (bounds['width'] / 2 if x_offset is None else x_offset),
                         bounds['y'] + bounds['height'] / 2)

    def verify_window(example, target):
        page.wait_for_selector(f'html[data-separate-window-tour="open:{example}"]', state='attached')
        assert page.locator('.tour-intro').is_hidden(), 'The live CSP must allow the extension to isolate a block'
        assert target.is_visible()
        assert worker.evaluate("(async()=> (await chrome.windows.getAll({windowTypes:['popup']})).length)()") == 1

    for example in ('video', 'chart', 'game'):
        target = page.locator('#practice-' + example)
        assert page.locator('#tour-next').is_hidden()
        if example == 'chart':
            wrong_target = page.locator('#chart-heading')
            detach(wrong_target)
            verify_window('other', wrong_target)
            click_toolbar('returnTitle')
            page.locator('#tour-status[data-kind=retry]').wait_for()
            assert page.locator('#tour-next').is_hidden()
        detach(target, x_offset=12 if example == 'game' else None)
        verify_window(example, target)
        if example == 'video':
            assert not target.evaluate('(video)=> video.paused')
            click_toolbar('pinTitle')
            page.locator('#practice-video').evaluate('''video => document.pictureInPictureElement === video ||
              new Promise(resolve => video.addEventListener('enterpictureinpicture', resolve, {once:true}))''')
            assert page.evaluate('document.pictureInPictureElement === document.querySelector("video")')
            click_toolbar('unpinTitle')
            page.locator('#practice-video').evaluate('''video => !document.pictureInPictureElement ||
              new Promise(resolve => video.addEventListener('leavepictureinpicture', resolve, {once:true}))''')
            assert not page.evaluate('document.pictureInPictureElement')
        elif example == 'chart':
            width = target.bounding_box()['width']
            click_toolbar('zoomOut')
            assert target.bounding_box()['width'] < width - 10
        else:
            tile = page.locator('.game-tile').first
            tile.click()
            assert tile.get_attribute('data-open') is not None
        click_toolbar('returnTitle')
        page.locator('#tour-next').wait_for()
        assert page.locator('.tour-intro').is_visible()
        if example == 'game':
            assert page.locator('.game-tile').first.get_attribute('data-open') is not None
        page.locator('#tour-next').click()

    assert page.locator('#tour-complete').is_visible()
    page.locator('#tour-complete-back').press('Enter')
    assert page.locator('#practice-game').is_visible()
    assert page.locator('.game-tile').first.get_attribute('data-open') is not None
    page.locator('#tour-next').click()
    page.reload()
    assert page.locator('#tour-complete').is_visible()
    for example in ('game', 'chart', 'video'):
        page.locator('#tour-complete-back' if example == 'game' else '#tour-back').click()
        assert page.locator('#practice-' + example).is_visible()
        assert page.locator('#tour-status[data-kind=success]').is_visible()
    assert page.locator('#tour-back').is_hidden()
    for _ in range(3):
        page.locator('#tour-next').click()
    page.locator('#tour-restart').click()
    assert page.locator('#practice-video').is_visible()
    assert page.locator('#tour-next').is_hidden()
    print('PASS: real video playback and PiP, chart zoom, Minesweeper, and back navigation with progress retained')


def main():
    with sync_playwright() as playwright:
        with tempfile.TemporaryDirectory(prefix='sw-tour-skip-') as profile:
            context = launch(playwright, profile)
            try:
                context.route(HOST + '/**', serve_site)
                worker, base, welcome = installed(context)
                assert not any(tab.url.startswith(HOST) for tab in context.pages)
                with welcome.expect_event('close', timeout=8000):
                    welcome.locator('[data-onboarding-choice=skip]').click()
                popup = context.new_page()
                popup.goto(base + '/popup.html')
                assert popup.locator('#onboarding-invite').is_hidden()
                assert worker.evaluate("(async()=> (await chrome.storage.local.get('onboarding')).onboarding)()") == 'skipped'
                popup.locator('[data-language=en]').click()
                popup.wait_for_function('document.documentElement.lang === "en"')
                with context.expect_page() as opened:
                    popup.get_by_role('button', name='Tutorial').click()
                english = opened.value
                english.wait_for_url(HOST + '/en/onboarding/')
                # Attach Playwright before intercepting the extension-created tab's navigation.
                english.goto(HOST + '/en/onboarding/')
                english.locator('html[lang=en]').wait_for(state='attached', timeout=8000)
                english.set_viewport_size({'width': 390, 'height': 844})
                assert english.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert english.get_by_role('button', name='Back', exact=True).count() == 0
                english.locator('#tour-skip').click()
                assert english.locator('#practice-chart').is_visible()
                english.get_by_role('button', name='Back', exact=True).click()
                assert english.locator('#practice-video').is_visible()
                english.evaluate("""sessionStorage.setItem('separate-window-tour', JSON.stringify({step: 1, practiced: true}))""")
                english.reload()
                assert english.locator('#practice-chart').is_visible()
                assert english.locator('#tour-next').is_visible()
                print('PASS: automatic local invite, opt-out, voluntary replay in English and mobile layout')
            finally:
                context.close()
        with tempfile.TemporaryDirectory(prefix='sw-tour-start-') as profile:
            context = launch(playwright, profile)
            try:
                context.route(HOST + '/**', serve_site)
                worker, base, welcome = installed(context)
                welcome.close()
                worker.evaluate("async () => {await chrome.storage.local.set({language:'ru'}); await SWI18n.reload();}")
                popup = context.new_page()
                popup.goto(base + '/popup.html')
                popup.locator('#onboarding-invite[open]').wait_for()
                with context.expect_page() as opened:
                    popup.get_by_role('button', name='Начать обучение').click()
                russian = opened.value
                russian.wait_for_url(HOST + '/onboarding/')
                russian.goto(HOST + '/onboarding/')
                russian.locator('html[lang=ru]').wait_for(state='attached', timeout=8000)
                assert popup.locator('#onboarding-invite').is_hidden()
                exercise(russian, worker, context)
                print('PASS: unresolved invite shows on first popup and goes away when the tour starts')
            finally:
                context.close()


if __name__ == '__main__':
    main()
