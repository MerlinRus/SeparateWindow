"""PiP integration: nested video players and a live preview of a widget."""
import json
import socket
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from smoke import Handler, ROOT

STREAM = '''<script>window.identity=crypto.randomUUID();
const c=document.createElement('canvas');c.width=640;c.height=360;
setInterval(()=>{const x=c.getContext('2d');x.fillStyle='blue';x.fillRect(0,0,640,360)},50);
document.querySelector('video').srcObject=c.captureStream(10);</script>'''


class PipHandler(Handler):
    def do_GET(self):
        port = self.server.server_port
        player = '<style>body{margin:0}video{width:100%;height:100%}#player-panel{position:fixed;inset:0;background:#0004}</style><video autoplay muted controls></video><div id="player-panel"><select><option>Season 6</option></select><button>Next episode</button></div>' + STREAM
        path = urlsplit(self.path).path
        pages = {
            '/pip': f'''<style>body{{margin:0}}video{{width:900px;height:500px}}iframe{{width:500px;height:300px}}</style>
                <video id="decoy" autoplay muted></video>
                <section id="widget" style="width:400px;height:240px;background:#1430d0">
                    <button style="position:absolute;bottom:20px;left:20px"
                        onclick="this.parentElement.style.background='#15d830';this.textContent='Updated'">Update</button>
                    <video id="tiny" style="width:8px;height:8px" autoplay muted></video>
                </section>
                <iframe id="player" src="http://localhost:{port}/nested"></iframe>''' + STREAM + '''
                <script>document.querySelector('#tiny').srcObject = document.querySelector('#decoy').srcObject;</script>''',
            '/shadow': '''<style>body{margin:0}#shadow-player{width:640px;height:360px}</style>
                <div id="shadow-player"></div><video id="decoy" autoplay muted></video>''' + STREAM + '''
                <script>const root = document.querySelector('#shadow-player').attachShadow({mode: 'closed'});
                root.innerHTML = '<video style="width:100%;height:100%" autoplay muted controls></video><button id="shadow-hud" style="position:absolute;top:0">Settings</button>';
                window.selectedVideo = root.querySelector('video');
                window.shadowHud = root.querySelector('#shadow-hud');
                selectedVideo.srcObject = document.querySelector('#decoy').srcObject;</script>''',
            '/nested': f'''<style>body{{margin:0}}iframe{{width:100%;height:100%;border:0}}</style>
                <iframe src="http://127.0.0.1:{port}/video"></iframe><button id="frame-panel" style="position:fixed;top:0">Season</button>''',
            '/closed-frames': f'''<style>body{{margin:0}}section{{width:640px;height:360px}}aside{{width:950px;height:500px}}</style>
                <section id="closed-player"></section><aside id="other-player"></aside><script>
                for (const [id, source] of [['closed-player', 'http://localhost:{port}/closed-inner'],
                    ['other-player', 'http://localhost:{port}/video?unrelated']]) {{
                    const root = document.getElementById(id).attachShadow({{mode: 'closed'}});
                    root.innerHTML = '<iframe style="width:100%;height:100%;border:0" src="'+source+'"></iframe>';
                }}</script>''',
            '/closed-inner': f'''<div id="nested-host" style="position:fixed;inset:0"></div><script>
                document.getElementById('nested-host').attachShadow({{mode: 'closed'}}).innerHTML =
                    '<iframe style="width:100%;height:100%;border:0" src="http://127.0.0.1:{port}/video?selected"></iframe>';
                </script>''',
            '/player-hud': '''<html class="site-layout"><style>body{margin:0}header{height:24px}
                html.site-layout{overflow:scroll!important}
                #movie_player{position:relative;width:720px;height:405px;overflow:auto}
                #surface,video{width:100%;height:100%}#player-controls{position:absolute;top:24px;width:720px;height:405px;pointer-events:none}
                #surface-hit{position:absolute;inset:30% 30% 30% 30%;background:none;border:0;pointer-events:auto}
                #hud{position:absolute;bottom:0;left:0;right:0;background:white;pointer-events:auto}
                #seek{width:100%;height:16px;background:#aaa}
                #quality-menu{position:absolute;bottom:30px;right:0;background:white}</style>
                <body><header>Page outside the player</header><div id="movie_player" class="html5-video-player">
                <div id="surface" class="html5-video-container"><video class="html5-main-video" style="width:760px;height:430px" autoplay muted></video></div></div>
                <div id="player-controls"><button id="surface-hit" aria-label="Play or pause"></button>
                <div id="hud"><div id="seek" role="slider" aria-label="Seek"></div><button id="settings">Settings</button>
                <button id="fullscreen">Fullscreen</button></div>
                <div id="quality-menu" hidden><button id="hd">1080p</button></div></div>''' + STREAM + '''
                <script>const movie = document.querySelector('#movie_player');
                const video = movie.querySelector('video');
                const overlay = document.querySelector('#player-controls');
                overlay.querySelector('#surface-hit').onclick = () => video.paused ? video.play() : video.pause();
                overlay.addEventListener('dblclick', () => movie.requestFullscreen());
                overlay.querySelector('#fullscreen').onclick = () => movie.requestFullscreen();
                overlay.querySelector('#settings').onclick = () => overlay.querySelector('#quality-menu').hidden = false;
                overlay.querySelector('#hd').onclick = () => {movie.dataset.quality = '1080p';overlay.querySelector('#quality-menu').hidden = true;};
                const timeline = overlay.querySelector('#seek');
                function percentage(event) {
                    return Math.round(100 * (event.clientX - timeline.getBoundingClientRect().left) / timeline.clientWidth);
                }
                timeline.onpointermove = event => {movie.dataset.hover = percentage(event);};
                timeline.onclick = event => {movie.dataset.seek = percentage(event);};</script>
                <style>#quality-menu{pointer-events:auto}</style>''',
            '/video': player,
            '/unready': '<video id="unready" controls style="width:640px;height:360px"></video>',
            '/unready-shell': '<vk-video-player id="unready" style="display:block;width:640px;height:360px">Loading</vk-video-player>',
        }
        if path not in pages:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(pages[path].encode())


def test_auto_pip_callback(page, worker):
    url = 'https://separate-window.test/auto-pip'
    html = '''<video id="main-video" autoplay muted style="width:640px;height:360px"></video>''' + STREAM + '''
        <video id="small-video" autoplay muted style="width:160px;height:90px"></video>
        <script>document.querySelector('#small-video').srcObject = document.querySelector('video').srcObject;</script>'''
    page.route(url, lambda route: route.fulfill(content_type='text/html', body=html))
    page.goto(url)
    page.wait_for_function("[...document.querySelectorAll('video')].every(video => video.videoWidth && !video.paused)")
    tab_id = worker.evaluate('''async url => {
        const [tab] = await chrome.tabs.query({url});
        await chrome.scripting.executeScript({target: {tabId: tab.id}, func: () => {
            navigator.mediaSession.setActionHandler = (action, callback) => {
                if (action === 'enterpictureinpicture') globalThis.autoPipTestCallback = callback;
            };
        }});
        return tab.id;
    }''', url)

    def set_enabled(enabled):
        return worker.evaluate('''async ([tabId, enabled]) => {
            const result = await handle({type: 'auto-pip', enabled, tabId}, {url: chrome.runtime.getURL('popup.html')});
            const [probe] = await chrome.scripting.executeScript({target: {tabId}, func: () => !!globalThis.autoPipTestCallback});
            return [result.enabled, probe.result];
        }''', [tab_id, enabled])

    assert set_enabled(True) == [True, True]

    def invoke_callback():
        return worker.evaluate('''async tabId => {
            const [result] = await chrome.scripting.executeScript({target: {tabId}, func: async () => {
                const attempted = [];
                for (const video of document.querySelectorAll('video')) {
                    video.requestPictureInPicture = async () => {attempted.push(video.id);};
                }
                await globalThis.autoPipTestCallback({reason: 'contentoccluded'});
                return attempted;
            }});
            return result.result;
        }''', tab_id)

    assert invoke_callback() == ['main-video']
    page.evaluate("document.querySelector('#main-video').pause()")
    assert invoke_callback() == ['small-video']
    page.evaluate("document.querySelector('#small-video').disablePictureInPicture = true")
    assert invoke_callback() == []
    page.evaluate("document.querySelector('#main-video').play()")
    page.locator('#main-video').click()
    worker.evaluate('''async tabId => {
        await chrome.scripting.executeScript({target: {tabId}, func: async () => {
            for (const video of document.querySelectorAll('video')) delete video.requestPictureInPicture;
            await globalThis.autoPipTestCallback({reason: 'contentoccluded'});
        }});
    }''', tab_id)
    page.wait_for_function("document.pictureInPictureElement?.id === 'main-video'")
    page.evaluate('document.exitPictureInPicture()')
    assert set_enabled(False) == [False, False]
    print('PASS: the site opt-in installs/removes the Auto PiP callback, which opens native PiP for the selected playing video', flush=True)


def test_widget_preview(page, worker, video_frame, node_with, button, labels, select_widget, restore_widget):
    def detach_widget():
        page.wait_for_function('document.querySelector("#tiny").readyState >= 2')
        select_widget()
        page.locator('#widget').scroll_into_view_if_needed()
        box = page.locator('#widget').bounding_box()
        page.mouse.click(box['x'] + 20, box['y'] + box['height'] / 2)
        page.wait_for_function('document.querySelector("#widget").getAttributeNames().some(x=>x.endsWith("-target"))')

    def open_preview():
        button('pinTitle')
        try:
            page.wait_for_function('!!documentPictureInPicture.window', timeout=6500)
        except Exception:
            button('pinPreviewContinueTitle')
        page.wait_for_function('documentPictureInPicture.window?.document.querySelector("video")?.readyState >= 2')
        page.evaluate('window.widgetTrack = documentPictureInPicture.window.document.querySelector("video").srcObject.getVideoTracks()[0]')

    detach_widget()
    open_preview()
    settings = page.evaluate('widgetTrack.getSettings()')
    assert settings['frameRate'] == 120, settings

    def preview_color(channel):
        pixels = '''() => {
            const video = documentPictureInPicture.window?.document.querySelector('video');
            if (!video?.videoWidth) return [];
            const canvas = document.createElement('canvas');
            canvas.width = canvas.height = 1;
            const ctx = canvas.getContext('2d');
            return [0.25, 0.5, 0.75].map(frac => {
                ctx.drawImage(video, video.videoWidth * frac, video.videoHeight / 2, 1, 1, 0, 0, 1, 1);
                return [...ctx.getImageData(0, 0, 1, 1).data];
            });
        }'''
        try:
            page.wait_for_function(f'channel => ({pixels})().some(rgb => rgb[channel] > 180)', arg=channel, timeout=5000)
        except Exception as error:
            raise AssertionError(page.evaluate(pixels)) from error

    preview_color(2)
    page.locator('#widget button').click()
    assert page.locator('#widget button').inner_text() == 'Updated'
    preview_color(1)
    assert not page.evaluate('!!document.pictureInPictureElement')
    assert not video_frame.evaluate('!!document.pictureInPictureElement')
    geometry = '''() => {const win = documentPictureInPicture.window;
        return {width: win.innerWidth, height: win.innerHeight, left: win.screenX, top: win.screenY};}'''
    original = page.evaluate(geometry)
    page.evaluate('documentPictureInPicture.window.resizeBy(92, 56)')
    page.wait_for_function(f'original => ({geometry})().width !== original.width', arg=original, timeout=3000)
    resized = page.evaluate(geometry)
    assert resized['width'] != original['width'] and resized['height'] != original['height'], resized
    expected_size = {key: resized[key] for key in ('width', 'height')}
    page.evaluate('documentPictureInPicture.window.close()')
    page.wait_for_function('widgetTrack.readyState === "ended" && !documentPictureInPicture.window')
    assert worker.evaluate('''async expected => {
        for (let i = 0; i < 30; i++) {
            const {pipPreviewSize} = await chrome.storage.local.get('pipPreviewSize');
            if (pipPreviewSize?.width === expected.width && pipPreviewSize.height === expected.height) return true;
            await new Promise(resolve => setTimeout(resolve, 50));
        }
        return false;
    }''', expected_size), expected_size
    assert node_with('aria-label', labels['pinTitle'])
    open_preview()
    assert page.evaluate(geometry) == resized, (resized, page.evaluate(geometry))
    restore_widget()
    page.wait_for_function('widgetTrack.readyState === "ended" && !documentPictureInPicture.window')
    assert page.locator('#widget button').inner_text() == 'Updated'
    page.reload()
    detach_widget()
    open_preview()
    reopened = page.evaluate(geometry)
    # Chrome rounds requested CSS pixels on displays with fractional DPI scaling.
    assert all(abs(reopened[key] - expected_size[key]) <= 1 for key in expected_size), (reopened, expected_size)
    restore_widget()
    page.wait_for_function('!documentPictureInPicture.window')
    print('PASS: widget preview negotiates 120 fps, updates live and stops capture on close or restore', flush=True)
    print('PASS: document PiP reopens at the last bounds and uses the saved size on a fresh page', flush=True)
def main():
    system_chrome = '--chrome' in sys.argv
    server = ThreadingHTTPServer(('127.0.0.1', 0), PipHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/pip'
    try:
        with tempfile.TemporaryDirectory(prefix='sw-pip-') as profile, sync_playwright() as p:
            headless = '--headed' not in sys.argv
            if system_chrome:
                # Branded Chrome loads unpacked extensions through browser-level CDP.
                with socket.socket() as server_socket:
                    server_socket.bind(('127.0.0.1', 0))
                    port = server_socket.getsockname()[1]
                browser = p.chromium.launch(channel='chrome', headless=headless,
                    ignore_default_args=['--disable-extensions'],
                    args=['--enable-unsafe-extension-debugging', '--auto-accept-this-tab-capture',
                          f'--remote-debugging-port={port}'])
                extension = browser.new_browser_cdp_session().send('Extensions.loadUnpacked', {'path': str(ROOT)})
                context = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}').contexts[0]
                page = context.new_page()
                page.goto(f'chrome-extension://{extension["id"]}/popup.html')
                close_browser = browser.close
            else:
                context = p.chromium.launch_persistent_context(profile, channel='chromium', headless=headless, viewport=None,
                    args=[f'--disable-extensions-except={ROOT}', f'--load-extension={ROOT}'])
                page = context.pages[0]
                close_browser = context.close
            try:
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                test_auto_pip_callback(page, worker)
                if '--auto-only' in sys.argv:
                    return
                labels = worker.evaluate("Object.fromEntries(['pinTitle','unpinTitle','pinPreviewContinueTitle','pipBlocked','pipNoVideo','showPlayer','onlyVideo','zoomOut'].map(k=>[k,chrome.i18n.getMessage(k)]))")
                page.goto(url)
                video_frame = next(frame for frame in page.frames if frame.url.endswith('/video'))
                video_frame.wait_for_function('document.querySelector("video").readyState>=2')
                identity = video_frame.evaluate('window.identity')
                video_time = video_frame.locator('video').evaluate('(v)=>v.currentTime')
                page.locator('#player').scroll_into_view_if_needed()
                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select')}''', url)
                box = page.locator('#player').bounding_box()
                page.mouse.click(box['x'] + 100, box['y'] + 100)
                page.wait_for_function('document.querySelector("#player").getAttributeNames().some(x=>x.endsWith("-target"))')
                cdp = context.new_cdp_session(page)

                def node_with(attribute, value):
                    def find(node):
                        attrs = node.get('attributes', [])
                        if dict(zip(attrs[::2], attrs[1::2])).get(attribute) == value:
                            return node
                        for child in node.get('children', []) + node.get('shadowRoots', []):
                            result = find(child)
                            if result:
                                return result
                    return find(cdp.send('DOM.getDocument', {'depth': -1, 'pierce': True})['root'])

                def button(key):
                    node = node_with('aria-label', labels[key])
                    assert node, key
                    obj = cdp.send('DOM.resolveNode', {'nodeId': node['nodeId']})['object']['objectId']
                    rect = cdp.send('Runtime.callFunctionOn', {'objectId': obj, 'functionDeclaration': 'function(){const r=this.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]}', 'returnByValue': True})['result']['value']
                    page.mouse.move(*rect)
                    page.mouse.click(*rect)

                nested_frame = next(frame for frame in page.frames if frame.url.endswith('/nested'))
                video_frame.locator('#player-panel').wait_for(state='visible', timeout=3000)
                assert nested_frame.locator('#frame-panel').is_visible()
                assert video_frame.locator('video').evaluate('(v)=>v.controls')
                button('onlyVideo')
                video_frame.locator('#player-panel').wait_for(state='hidden')
                assert not nested_frame.locator('#frame-panel').is_visible()
                assert not video_frame.locator('video').evaluate('(v)=>v.controls')
                assert page.locator('#player').evaluate('(e)=>getComputedStyle(e).borderTopWidth') == '0px'
                assert video_frame.evaluate('window.identity') == identity
                page.screenshot(path=str(ROOT/'tests/clean-video.png'))
                button('showPlayer')
                video_frame.locator('#player-panel').wait_for(state='visible')
                assert video_frame.locator('video').evaluate('(v)=>v.controls')
                print('PASS: native controls by default, optional clean video and restoration without reload', flush=True)
                button('pinTitle')
                video_frame.wait_for_function('!!document.pictureInPictureElement', timeout=5000)
                assert not page.evaluate('!!document.pictureInPictureElement'), 'A larger unrelated video must never be selected'
                assert video_frame.evaluate('window.identity') == identity
                assert video_frame.locator('video').evaluate('(v)=>v.currentTime') >= video_time
                button('unpinTitle')
                video_frame.wait_for_function('!document.pictureInPictureElement')
                button('pinTitle')
                video_frame.wait_for_function('!!document.pictureInPictureElement')
                video_frame.evaluate('document.exitPictureInPicture()')
                page.wait_for_timeout(150)
                assert node_with('aria-label', labels['pinTitle'])
                print('PASS: nested cross-origin video, no decoy selection/reload, toggle and native-close feedback', flush=True)

                video_frame.locator('video').evaluate('(v)=>v.disablePictureInPicture=true')
                button('pinTitle')
                page.wait_for_timeout(250)
                notice = node_with('role', 'status')
                assert notice and labels['pipBlocked'] in json.dumps(notice, ensure_ascii=False)
                assert not video_frame.evaluate('!!document.pictureInPictureElement')
                print('PASS: player PiP restriction is respected and explained', flush=True)

                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await restore(tab.id)}''', url)
                assert video_frame.locator('#player-panel').is_visible()
                assert nested_frame.locator('#frame-panel').is_visible()
                assert video_frame.locator('video').evaluate('(v)=>v.controls')
                if system_chrome:
                    def select_widget():
                        worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select')}''', url)
                    def restore_widget():
                        worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await restore(tab.id)}''', url)
                    test_widget_preview(page, worker, video_frame, node_with, button, labels, select_widget, restore_widget)

                shadow_url = url.replace('/pip', '/shadow')
                page.goto(shadow_url)
                page.wait_for_function('selectedVideo.readyState >= 2 && selectedVideo.currentTime > 0')
                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select')}''', shadow_url)
                page.mouse.click(120, 120)
                page.wait_for_function('document.querySelector("#shadow-player").getAttributeNames().some(x=>x.endsWith("-target"))')
                page.locator('#shadow-player').evaluate("(player) => {player.style.width = '640px'; player.style.height = '360px'; player.id = 'updated-player'}")
                button('onlyVideo')
                page.wait_for_function('!selectedVideo.controls && getComputedStyle(shadowHud).display === "none"', timeout=2000)
                button('showPlayer')
                page.wait_for_function('selectedVideo.controls && getComputedStyle(shadowHud).display !== "none"')
                print('PASS: only-video mode hides and restores controls inside a closed player root', flush=True)
                button('pinTitle')
                page.wait_for_timeout(300)
                notice = node_with('role', 'status')
                assert not notice, json.dumps(notice, ensure_ascii=True)
                page.wait_for_function('selectedVideo.getRootNode().pictureInPictureElement === selectedVideo', timeout=5000)
                button('unpinTitle')
                page.wait_for_function('!document.pictureInPictureElement', timeout=5000)
                print('PASS: video in a closed player root opens and closes in PiP', flush=True)

                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await restore(tab.id)}''', shadow_url)
                closed_url = url.replace('/pip', '/closed-frames')
                page.goto(closed_url)
                selected_frame = next(frame for frame in page.frames if frame.url.endswith('/video?selected'))
                decoy_frame = next(frame for frame in page.frames if frame.url.endswith('/video?unrelated'))
                selected_frame.wait_for_function('document.querySelector("video").readyState >= 2')
                decoy_frame.wait_for_function('document.querySelector("video").readyState >= 2')
                assert page.evaluate('window.length') == 0, 'Closed frames must be absent from the indexed frame list'
                identity = selected_frame.evaluate('window.identity')
                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select')}''', closed_url)
                page.mouse.click(120, 120)
                page.wait_for_function('document.querySelector("#closed-player").getAttributeNames().some(x=>x.endsWith("-target"))')
                button('pinTitle')
                try:
                    selected_frame.wait_for_function('!!document.pictureInPictureElement', timeout=3000)
                except Exception as error:
                    raise AssertionError(json.dumps(node_with('role', 'status'), ensure_ascii=True)) from error
                assert not decoy_frame.evaluate('!!document.pictureInPictureElement')
                assert selected_frame.evaluate('window.identity') == identity
                button('unpinTitle')
                selected_frame.wait_for_function('!document.pictureInPictureElement')
                print('PASS: nested cross-origin iframes in closed components pin only the selected video', flush=True)

                button('pinTitle')
                selected_frame.wait_for_function('!!document.pictureInPictureElement', timeout=5000)
                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await toggleSelection(tab.id)}''', closed_url)
                selected_frame.wait_for_function('!document.pictureInPictureElement', timeout=5000)
                print('PASS: returning to the tab also closes extension-owned PiP in a nested frame', flush=True)
                hud_url = url.replace('/pip', '/player-hud')
                page.goto(hud_url)
                page.wait_for_function('document.querySelector("video").currentTime > 0')
                identity = page.evaluate('window.identity')
                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select')}''', hud_url)
                box = page.locator('video').bounding_box()
                page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                page.wait_for_function('document.querySelector("#movie_player").getAttributeNames().some(x=>x.endsWith("-target"))', timeout=5000)
                assert not page.locator('header').is_visible()
                assert not page.locator('video').evaluate('(v)=>v.paused'), 'Selection must not pause the player'
                page.locator('#surface-hit').click()
                assert page.locator('video').evaluate('(v)=>v.paused'), 'A single click should reach play/pause'
                assert not page.evaluate('document.fullscreenElement'), 'A single click must not enter fullscreen'
                page.locator('#settings').click()
                page.locator('#hd').click()
                assert page.locator('#movie_player').get_attribute('data-quality') == '1080p'
                movie = page.locator('#movie_player')

                def check_timeline():
                    seek = page.locator('#seek')
                    rect = seek.bounding_box()
                    point = (rect['x'] + rect['width'] * .70, rect['y'] + rect['height'] / 2)
                    page.mouse.move(*point)
                    hover = movie.get_attribute('data-hover')
                    assert hover is not None and abs(int(hover) - 70) <= 1, (page.viewport_size, hover)
                    page.mouse.click(*point)
                    assert abs(int(movie.get_attribute('data-seek')) - 70) <= 1
                    assert page.evaluate('''() => {
                        const root = document.documentElement;
                        const player = document.querySelector('#movie_player');
                        return getComputedStyle(root).overflow === 'hidden' &&
                            root.clientWidth === innerWidth && root.clientHeight === innerHeight &&
                            getComputedStyle(player).overflow === 'hidden';
                    }'''), 'Separate window must not expose document or player scrollbars'

                for width, height in [(640, 360), (1030, 490)]:
                    page.set_viewport_size({'width': width, 'height': height})
                    check_timeline()
                before_zoom = movie.bounding_box()['width']
                button('zoomOut')
                page.wait_for_function('(width) => document.querySelector("#movie_player").clientWidth < width - 20', arg=before_zoom)
                check_timeline()
                print('PASS: timeline hover and clicks agree at 70% after resizing and manual zoom, with no scrollbars', flush=True)
                button('onlyVideo')
                page.locator('#player-controls').wait_for(state='hidden')
                button('showPlayer')
                page.locator('#player-controls').wait_for(state='visible')
                page.locator('#fullscreen').click()
                page.wait_for_function('document.fullscreenElement?.id === "movie_player"', timeout=5000)
                assert page.locator('#movie_player').evaluate('(e)=>Math.abs(e.getBoundingClientRect().width - innerWidth)<1')
                page.evaluate('document.exitFullscreen()')
                assert page.evaluate('window.identity') == identity
                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await restore(tab.id)}''', hud_url)
                assert page.evaluate('getComputedStyle(document.documentElement).overflow') == 'scroll'
                print('PASS: player picked from the video surface, settings/seek reachable, single-click pause and explicit fullscreen', flush=True)

                for path in ('/unready', '/unready-shell'):
                    unready_url = url.replace('/pip', path)
                    page.goto(unready_url)
                    worker.evaluate('''async url => {
                        const [tab] = await chrome.tabs.query({url});
                        await tell(tab.id, 'select');
                        await chrome.scripting.executeScript({target: {tabId: tab.id}, func: () => {
                            navigator.mediaDevices.getDisplayMedia = () => {
                                document.documentElement.dataset.captureRequested = 'yes';
                                return Promise.reject(new Error('Unexpected tab capture'));
                            };
                        }});
                    }''', unready_url)
                    page.mouse.click(140, 120)
                    page.wait_for_function('document.querySelector("#unready").getAttributeNames().some(a=>a.endsWith("-target"))')
                    button('pinTitle')
                    page.wait_for_timeout(350)
                    notice = node_with('role', 'status')
                    assert notice and labels['pipNoVideo'] in json.dumps(notice, ensure_ascii=False), path
                    assert page.evaluate('document.documentElement.dataset.captureRequested === undefined')
                    worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await restore(tab.id)}''', unready_url)
                print('PASS: an unready video explains how to start PiP without asking to capture the tab', flush=True)

            finally:
                close_browser()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
