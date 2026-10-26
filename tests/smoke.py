"""Real Chromium + unpacked MV3 smoke test. Requires Python playwright."""
import json
from pathlib import Path
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = b'''<!doctype html><meta charset="utf-8"><style>
body{margin:0;background:#eee;font:18px sans-serif}header{padding:20px}
#container{margin:30px;transform:translateZ(0);overflow:hidden}
#widget{width:500px;height:300px;background:#2855b0;color:white;display:flex;align-items:center;justify-content:center}
button{font:22px sans-serif;padding:12px}iframe{width:200px;height:100px}
</style><header>Outside selection</header><main id="container"><section id="widget">
<button id="counter" onclick="this.textContent=++window.count">0</button>
<iframe srcdoc="<button onclick='this.textContent=Number(this.textContent)+1'>0</button>"></iframe>
<video autoplay muted width="80" height="60"></video>
</section></main><script>window.count=0;window.identity=crypto.randomUUID();
const canvas=document.createElement('canvas');const ctx=canvas.getContext('2d');
setInterval(()=>{ctx.fillStyle='orange';ctx.fillRect(0,0,300,150)},50);
document.querySelector('video').srcObject=canvas.captureStream(10);
</script>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(FIXTURE)

    def log_message(self, *args):
        pass


def main():
    print('Starting local fixture and isolated Chromium...', flush=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    with tempfile.TemporaryDirectory(prefix='separate-window-test-') as profile, sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile, channel='chromium', headless=True, viewport=None,
            args=[f'--disable-extensions-except={ROOT}', f'--load-extension={ROOT}', '--no-first-run'],
            accept_downloads=True, timeout=20000,
        )
        try:
            print('Chromium launched; waiting for MV3 worker...', flush=True)
            worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
            errors = []
            worker.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
            page = context.pages[0]
            page.goto(url)
            print('Fixture loaded; testing picker...', flush=True)
            page.wait_for_function('window.__separateWindowLocal === undefined')  # isolated world stays isolated
            identity = page.evaluate('window.identity')
            page.locator('#counter').click()
            page.frame_locator('iframe').get_by_role('button').click()
            page.wait_for_function("document.querySelector('video').currentTime > 0")
            video_time = page.locator('video').evaluate('(v)=>v.currentTime')

            def command(kind):
                return worker.evaluate('''async ({url,kind}) => {
                  const [tab] = await chrome.tabs.query({url});
                  return handle({type:kind, tabId:tab.id}, {url:chrome.runtime.getURL('popup.html')});
                }''', {'url': url + '*', 'kind': kind})

            def state():
                return worker.evaluate('''async () => {
                  const windows = await chrome.windows.getAll({populate:true});
                  const session = await chrome.storage.session.get(null);
                  const local = await chrome.storage.local.get(null);
                  return {windows,session,local};
                }''')

            command('select')
            page.keyboard.press('Escape')
            command('select')
            print('Picker activated', flush=True)
            box = page.locator('#counter').bounding_box()
            x, y = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
            page.mouse.move(x, y)
            page.mouse.wheel(0, 100)  # counter -> section
            page.wait_for_timeout(150)
            page.mouse.click(x, y)
            print('Selection clicked', page.locator('#widget').evaluate('(e)=>e.getAttributeNames()'), flush=True)
            page.wait_for_function("document.querySelector('[id=widget]').getAttributeNames().some(x=>x.endsWith('-target'))")
            page.wait_for_timeout(400)
            result = state()
            assert any(w['type'] == 'popup' for w in result['windows']), result
            assert page.evaluate('window.identity') == identity
            assert page.locator('#counter').text_content() == '1'
            assert page.locator('header').is_hidden()
            assert result['local'][f'selection:{url}']['selector'] == '#widget', result['local']
            page.set_viewport_size({'width': 500, 'height': 350})
            page.locator('#counter').click()
            assert page.locator('#counter').text_content() == '2'
            assert page.frame_locator('iframe').get_by_role('button').text_content() == '1'
            assert page.locator('video').evaluate('(v)=>v.currentTime') >= video_time
            assert page.locator('#widget').evaluate('(e)=>getComputedStyle(e).display') == 'flex'
            page.screenshot(path=str(ROOT / 'tests' / 'window-preview.png'))
            print('PASS: picker, wheel, popup, hidden siblings, live click handler, no reload')

            # Closed Shadow DOM is intentional. Use CDP to inspect test toolbar controls.
            cdp = context.new_cdp_session(page)
            cdp.send('DOM.enable')

            def click_control(label):
                tree = cdp.send('DOM.getDocument', {'depth': -1, 'pierce': True})
                def find(node):
                    attrs = node.get('attributes', [])
                    pairs = dict(zip(attrs[::2], attrs[1::2]))
                    if pairs.get('aria-label') == label:
                        return node
                    for child in node.get('children', []) + node.get('shadowRoots', []):
                        match = find(child)
                        if match:
                            return match
                node = find(tree['root'])
                assert node, label
                obj = cdp.send('DOM.resolveNode', {'nodeId': node['nodeId']})['object']['objectId']
                cdp.send('Runtime.callFunctionOn', {'objectId': obj, 'functionDeclaration': 'function(){this.click()} '})

            click_control('Сохранить или забыть размер и положение окна')
            page.wait_for_timeout(200)
            assert state()['local'][f'selection:{url}']['bounds']['width'] > 0
            click_control('Сохранить или забыть размер и положение окна')
            page.wait_for_timeout(150)
            assert 'bounds' not in state()['local'][f'selection:{url}']
            click_control('Сохранить или забыть размер и положение окна')
            page.wait_for_timeout(150)
            click_control('Повернуть на 90°')
            assert 'matrix' in page.locator('#widget').evaluate('(e)=>getComputedStyle(e).transform')
            click_control('Повернуть на 90°')
            click_control('Повернуть на 90°')
            click_control('Повернуть на 90°')
            print('PASS: saved window geometry, rotation')

            with page.expect_download() as download:
                click_control('Сохранить видимую область блока в PNG')
            path = Path(download.value.path())
            assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            print(f'PASS: screenshot download ({path.stat().st_size} bytes)')

            click_control('Сохранить в закладки Separate windows')
            page.wait_for_timeout(200)
            bookmarks = worker.evaluate("chrome.bookmarks.search({title:'Separate windows'}).then(async a=>chrome.bookmarks.getChildren(a[0].id))")
            link = bookmarks[0]['url']
            assert '#__sw_local=' in link, bookmarks
            print('PASS: bookmark folder and automatic-open link')

            command('restore')
            page.wait_for_timeout(200)
            assert page.locator('header').is_visible()
            assert page.evaluate('window.identity') == identity
            assert page.locator('#counter').text_content() == '2'
            assert page.frame_locator('iframe').get_by_role('button').text_content() == '1'
            assert page.locator('video').evaluate('(v)=>v.currentTime') >= video_time
            assert not state()['session']
            assert len(context.pages) == 1, 'Temporary blank tab must be removed'
            print('PASS: return to original window and original layout/state')

            page.goto(link)
            page.wait_for_timeout(600)
            assert page.url == url, page.url
            assert any(w['type'] == 'popup' for w in state()['windows'])
            assert page.locator('header').is_hidden()
            command('restore')
            page.reload()
            page.wait_for_timeout(300)
            # Revisit marker visible, without automatic detachment for ordinary URLs.
            assert not state()['session']
            command('forget')
            page.wait_for_timeout(150)
            assert f'selection:{url}' not in state()['local']
            assert not errors, errors
            print('PASS: automatic link, normal revisit, forget selection, clean worker console')
            page.screenshot(path=str(ROOT / 'tests' / 'verified-page.png'))
            print('ALL SMOKE CHECKS PASSED')
        except Exception:
            page.screenshot(path=str(ROOT / 'tests' / 'failure.png'))
            print('Failure state:', json.dumps(state(), ensure_ascii=True), flush=True)
            raise
        finally:
            context.close()
            server.shutdown()


if __name__ == '__main__':
    main()
