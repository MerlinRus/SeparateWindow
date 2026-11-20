"""Exercise detached Twitch and embedded-player layout through the real picker."""

import tempfile
import threading
from http.server import ThreadingHTTPServer

from playwright.sync_api import sync_playwright

from smoke import Handler, ROOT


TWITCH_LAYOUT = '''<!doctype html><html class="site"><meta charset="utf-8">
<style>
  html.site { overflow: scroll !important; }
  body { margin: 0; }
  header { height: 50px; }
  main { position: relative; width: 1400px; height: 900px; }
  .persistent-player { position: absolute; width: 864px; height: 486px; }
  .video-player { position: absolute; inset: 0; }
  .video-player__container, video { position: absolute; inset: 0; width: 100%; height: 100%; }
  .video-player__container { overflow: hidden; }
  #hud { position: absolute; inset: auto 0 0; background: white; }
  #seek { height: 24px; background: lightgrey; }
  .tw-dialog-layer { position: relative; z-index: 2; }
  .tw-dialog-layer [role="menu"] { position: fixed; right: 24px; bottom: 64px; padding: 12px; background: white; }
</style>
<header>Navigation outside the selection</header>
<main><div class="persistent-player">
  <div id="temporary-player-id" class="video-player" data-a-target="video-player" data-test-selector="video-player__video-layout">
    <div class="video-player__container" data-test-selector="video-player__video-container"
         style="max-height: calc(100vh - 160px)">
      <div data-a-target="video-ref"><video autoplay muted></video></div>
    </div>
    <div id="hud"><div id="seek" role="slider" aria-label="Seek"></div>
      <button id="settings">Settings</button><button id="fullscreen">Fullscreen</button>
    </div>
  </div>
</div></main>
<div class="tw-dialog-layer" id="unrelated">Unrelated page dialog</div>
<script>
  const player = document.querySelector('.video-player');
  const video = document.querySelector('video');
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = 640; canvas.height = 360;
  let painted = false;
  setInterval(() => {
    painted = !painted;
    ctx.fillStyle = painted ? '#316cbf' : '#264166';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }, 50);
  video.srcObject = canvas.captureStream(20);
  window.originalVideo = video;
  video.onclick = () => video.paused ? video.play() : video.pause();
  document.querySelector('#settings').onclick = () => {
    const layer = document.createElement('div');
    layer.className = 'tw-dialog-layer';
    layer.innerHTML = '<div role="menu"><div data-a-target="player-settings-menu"><button id="quality">Quality</button></div></div>';
    document.body.append(layer);
    const menu = layer.querySelector('[data-a-target="player-settings-menu"]');
    menu.querySelector('#quality').onclick = () => {
      menu.innerHTML = '<button data-a-target="player-settings-submenu-quality-option">1080p</button>';
      menu.firstChild.onclick = () => { player.dataset.quality = '1080p'; layer.remove(); };
    };
  };
  document.querySelector('#fullscreen').onclick = () => player.requestFullscreen();
  const seek = document.querySelector('#seek');
  for (const [event, key] of [['pointermove', 'hover'], ['click', 'seek']]) {
    seek.addEventListener(event, e => {
      player.dataset[key] = Math.round(100 * (e.clientX - seek.getBoundingClientRect().left) / seek.clientWidth);
    });
  }
</script></html>'''

RUTUBE_EMBED_LAYOUT = '''<!doctype html><meta charset="utf-8">
<style>
  body { margin: 0; }
  .touch-handlers-layout-module__layout___test { width: 640px; height: 360px; position: relative; }
  video { width: 100%; height: 100%; }
  #settings { position: absolute; bottom: 12px; right: 12px; }
  #raichuSettingsPanel { position: fixed; bottom: 70px; right: 36px; padding: 12px; background: white; }
</style>
<main>
  <div class="touch-handlers-layout-module__layout___test">
    <video></video><button id="settings">Settings</button>
  </div>
  <div data-floating-ui-portal id="unrelated">Unrelated portal</div>
</main>
<script>
  document.querySelector('#settings').onclick = () => {
    const root = document.createElement('div');
    root.setAttribute('data-floating-ui-portal', '');
    root.innerHTML = '<div id="raichuSettingsPanel"><button data-testid="qualityButton">Quality</button></div>';
    document.querySelector('main').append(root);
    const menu = root.firstChild;
    menu.querySelector('button').onclick = () => {
      menu.innerHTML = '<button>720p</button>';
      menu.querySelector('button').onclick = () => {
        document.querySelector('video').dataset.quality = '720p';
        root.remove();
      };
    };
  };
</script>'''


class PlayerHandler(Handler):
    def do_GET(self):
        if self.path != '/twitch-layout':
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(TWITCH_LAYOUT.encode())


def test_embedded_player(page, worker, url):
    page.set_viewport_size({'width': 1280, 'height': 800})
    page.goto(url)
    iframe = page.locator('#movie')
    control = page.frame_locator('#movie').get_by_role('button')
    control.wait_for()
    frame = next(frame for frame in page.frames if frame.url.endswith('/frame'))
    identity = frame.evaluate('window.identity')
    worker.evaluate('''async url => {const [tab] = await chrome.tabs.query({url}); await tell(tab.id, 'select')}''', url)
    box = iframe.bounding_box()
    aspect = box['width'] / box['height']
    page.mouse.click(box['x'] + 200, box['y'] + 130)
    page.wait_for_function('''document.querySelector('#movie').getAttributeNames().some(key => key.endsWith('-target'))''')
    for width, height in [(1000, 600), (710, 460)]:
        page.set_viewport_size({'width': width, 'height': height})
        page.wait_for_function('''aspect => {
            const r = document.querySelector('#movie').getBoundingClientRect();
            return Math.abs(r.width - Math.min(innerWidth, innerHeight * aspect)) <= 1;
        }''', arg=aspect)
        frame_box = iframe.evaluate('''element => {
            const rect = element.getBoundingClientRect();
            return {visual: [rect.width, rect.height], box: [element.offsetWidth, element.offsetHeight],
                    inner: [element.clientWidth, element.clientHeight]};
        }''')
        assert all(abs(a - b) <= 1 for a, b in zip(frame_box['visual'], frame_box['box'])), frame_box
        assert frame.evaluate('[innerWidth,innerHeight]') == frame_box['inner'], frame_box
        assert frame.evaluate('window.identity') == identity
    control.click()
    assert frame.evaluate('window.hits') == 2
    worker.evaluate('''async url => {const [tab] = await chrome.tabs.query({url}); await restore(tab.id)}''', url)
    print('PASS: cross-origin embedded viewport follows popup resizing and preserves controls and state')


def test_rutube_settings(page, worker):
    url = 'https://rutube.ru/play/sw-test-settings/'
    page.route(url, lambda route: route.fulfill(content_type='text/html', body=RUTUBE_EMBED_LAYOUT))
    page.goto(url)
    worker.evaluate('''async url => {const [tab] = await chrome.tabs.query({url}); await tell(tab.id, 'select')}''', url)
    page.mouse.click(260, 140)
    page.wait_for_function('document.querySelector("video").parentElement.getAttributeNames().some(a=>a.endsWith("-target"))')
    page.locator('#settings').click()
    menu = page.locator('#raichuSettingsPanel')
    menu.wait_for(state='visible', timeout=1500)
    assert not page.locator('#unrelated').is_visible()
    menu.get_by_role('button', name='Quality').click()
    menu.get_by_role('button', name='720p').click()
    assert page.locator('video').get_attribute('data-quality') == '720p'
    worker.evaluate('''async url => {const [tab] = await chrome.tabs.query({url}); await restore(tab.id)}''', url)
    assert page.locator('#unrelated').is_visible()
    print('PASS: embedded RUTUBE settings and quality remain interactive, unrelated portals stay hidden')


def main():
    with ThreadingHTTPServer(('127.0.0.1', 0), PlayerHandler) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/twitch-layout'
        try:
            with tempfile.TemporaryDirectory(prefix='sw-layout-') as profile, sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    profile, channel='chromium', headless=True, viewport={'width': 1440, 'height': 900},
                    args=[f'--disable-extensions-except={ROOT}', f'--load-extension={ROOT}'],
                )
                try:
                    worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                    page = context.pages[0]
                    page.set_default_timeout(8000)
                    page.goto(url)
                    page.wait_for_function('originalVideo.readyState >= 2 && originalVideo.currentTime > 0')
                    worker.evaluate('''async url => {const [tab] = await chrome.tabs.query({url}); await tell(tab.id, 'select')}''', url)
                    source = page.locator('video').bounding_box()
                    page.mouse.click(source['x'] + 200, source['y'] + 160)
                    page.wait_for_function('''document.querySelector('.video-player').getAttributeNames().some(key => key.endsWith('-target'))''')
                    player = page.locator('.video-player')
                    assert not page.locator('header').is_visible()
                    assert not page.evaluate('originalVideo.paused')

                    for width, height in [(1210, 540), (640, 360), (1080, 730)]:
                        page.set_viewport_size({'width': width, 'height': height})
                        page.wait_for_function('''() => {
                            const r = document.querySelector('.video-player').getBoundingClientRect();
                            return Math.abs(r.height - Math.min(innerHeight, innerWidth * 9 / 16)) <= 1;
                        }''')
                        target, video = player.bounding_box(), page.locator('video').bounding_box()
                        assert all(abs(target[key] - video[key]) <= 1 for key in ('x', 'y', 'width', 'height')), (target, video)
                        state = page.evaluate('''() => {
                            const root = document.documentElement;
                            return [getComputedStyle(root).overflow, getComputedStyle(document.body).overflow,
                                    root.scrollWidth, root.scrollHeight, innerWidth, innerHeight];
                        }''')
                        assert state == ['hidden', 'hidden', width, height, width, height], state
                        timeline = page.locator('#seek').bounding_box()
                        point = (timeline['x'] + timeline['width'] * .7, timeline['y'] + timeline['height'] / 2)
                        page.mouse.move(*point)
                        assert abs(int(player.get_attribute('data-hover')) - 70) <= 1
                        page.mouse.click(*point)
                        assert abs(int(player.get_attribute('data-seek')) - 70) <= 1

                    page.locator('video').click(position={'x': 100, 'y': 100})
                    assert page.evaluate('originalVideo.paused && !document.fullscreenElement')
                    assert not page.locator('#unrelated').is_visible()
                    page.locator('#settings').click()
                    menu = page.locator('[data-a-target="player-settings-menu"]')
                    menu.wait_for(state='visible', timeout=1500)
                    menu.get_by_role('button', name='Quality').click()
                    menu.get_by_role('button', name='1080p').click()
                    assert player.get_attribute('data-quality') == '1080p'
                    assert not menu.count() and not page.locator('#unrelated').is_visible()
                    page.locator('#fullscreen').click()
                    page.wait_for_function('document.fullscreenElement === document.querySelector(".video-player")')
                    page.evaluate('document.exitFullscreen()')
                    saved = worker.evaluate('''async url => {
                        const key = `selection:${url}`;
                        return (await chrome.storage.local.get(key))[key].selector;
                    }''', url)
                    player.evaluate('element => { element.id = "new-player-id"; }')
                    assert page.evaluate('selector => document.querySelector(selector)?.matches(".video-player")', saved), saved
                    worker.evaluate('''async url => {const [tab] = await chrome.tabs.query({url}); await restore(tab.id)}''', url)
                    assert page.locator('header').is_visible()
                    assert page.locator('#unrelated').is_visible()
                    assert page.evaluate('originalVideo === document.querySelector("video")')
                    assert page.evaluate('getComputedStyle(document.documentElement).overflow') == 'scroll'
                    print('PASS: Twitch layout, controls, settings portal, quality selection, fullscreen and live restore')
                    test_embedded_player(page, worker, url.replace('/twitch-layout', '/embedded'))
                    test_rutube_settings(page, worker)
                finally:
                    context.close()
        finally:
            server.shutdown()


if __name__ == '__main__':
    main()
