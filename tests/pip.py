"""PiP integration: selected cross-origin/nested frames, decoys and denied players."""
import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright
from smoke import Handler, ROOT

STREAM = '''<script>window.identity=crypto.randomUUID();
const c=document.createElement('canvas');c.width=640;c.height=360;
setInterval(()=>{const x=c.getContext('2d');x.fillStyle='blue';x.fillRect(0,0,640,360)},50);
document.querySelector('video').srcObject=c.captureStream(10);</script>'''


class PipHandler(Handler):
    def do_GET(self):
        port = self.server.server_port
        pages = {
            '/pip': f'''<style>body{{margin:0}}video{{width:900px;height:500px}}iframe{{width:500px;height:300px}}</style>
                <video id="decoy" autoplay muted></video><section id="empty">No video</section>
                <iframe id="player" src="http://localhost:{port}/nested"></iframe>''' + STREAM,
            '/nested': f'''<style>body{{margin:0}}iframe{{width:100%;height:100%;border:0}}</style>
                <iframe src="http://127.0.0.1:{port}/video"></iframe><button id="frame-panel" style="position:fixed;top:0">Season</button>''',
            '/video': '<style>body{margin:0}video{width:100%;height:100%}#player-panel{position:fixed;inset:0;background:#0004}</style><video autoplay muted controls></video><div id="player-panel"><select><option>Season 6</option></select><button>Next episode</button></div>' + STREAM,
        }
        if self.path not in pages:
            return super().do_GET()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(pages[self.path].encode())


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), PipHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/pip'
    try:
        with tempfile.TemporaryDirectory(prefix='sw-pip-') as profile, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(profile, channel='chromium', headless=True, viewport=None,
                args=[f'--disable-extensions-except={ROOT}', f'--load-extension={ROOT}'])
            try:
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                labels = worker.evaluate("Object.fromEntries(['pinTitle','unpinTitle','pipNoVideo','pipBlocked','showPlayer','onlyVideo'].map(k=>[k,chrome.i18n.getMessage(k)]))")
                page = context.pages[0]
                page.goto(url)
                video_frame = next(frame for frame in page.frames if frame.url.endswith('/video'))
                video_frame.wait_for_function('document.querySelector("video").readyState>=2')
                identity = video_frame.evaluate('window.identity')
                video_time = video_frame.locator('video').evaluate('(v)=>v.currentTime')
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
                video_frame.locator('#player-panel').wait_for(state='hidden')
                assert not nested_frame.locator('#frame-panel').is_visible()
                assert not video_frame.locator('video').evaluate('(v)=>v.controls')
                assert page.locator('#player').evaluate('(e)=>getComputedStyle(e).borderTopWidth') == '0px'
                button('showPlayer')
                video_frame.locator('#player-panel').wait_for(state='visible')
                assert nested_frame.locator('#frame-panel').is_visible()
                assert video_frame.locator('video').evaluate('(v)=>v.controls')
                button('onlyVideo')
                video_frame.locator('#player-panel').wait_for(state='hidden')
                assert not video_frame.locator('video').evaluate('(v)=>v.controls')
                assert video_frame.evaluate('window.identity') == identity
                page.screenshot(path=str(ROOT/'tests/clean-video.png'))
                print('PASS: player overlays and native controls hidden across nested frames; reversible without reload', flush=True)
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

                worker.evaluate('''async url => {const [tab]=await chrome.tabs.query({url});await restore(tab.id);await tell(tab.id,'select')}''', url)
                assert video_frame.locator('#player-panel').is_visible()
                assert nested_frame.locator('#frame-panel').is_visible()
                assert video_frame.locator('video').evaluate('(v)=>v.controls')
                box = page.locator('#empty').bounding_box()
                page.mouse.click(box['x'] + 20, box['y'] + box['height'] / 2)
                page.wait_for_function('document.querySelector("#empty").getAttributeNames().some(x=>x.endsWith("-target"))')
                button('pinTitle')
                page.wait_for_timeout(250)
                notice = node_with('role', 'status')
                assert notice and labels['pipNoVideo'] in json.dumps(notice, ensure_ascii=False)
                assert not page.evaluate('!!document.pictureInPictureElement')
                assert not video_frame.evaluate('!!document.pictureInPictureElement')
                print('PASS: an empty selected block does not pin unrelated videos', flush=True)
            finally:
                context.close()
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
