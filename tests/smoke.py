"""Real Chromium + unpacked MV3 smoke test. Requires Python playwright."""
import json
import struct
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
window.playerEvents=0;
document.querySelector('video').addEventListener('pointerdown',event=>{window.playerEvents++;event.currentTarget.pause()});
</script>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        if self.path == '/embedded':
            self.wfile.write(f'''<!doctype html><style>
              body{{padding:70px 12px 50px;background:#334455}}
              body::after{{content:"";position:fixed;inset:0;background:linear-gradient(#aa000033,#0000);pointer-events:none}}
              .shell{{position:relative;background:linear-gradient(#803030,#305080);border:8px solid #e0a020;border-radius:24px;padding:22px;box-shadow:0 0 20px #f00}}
              .player-main{{position:relative;padding-bottom:60%;height:0;background:#161616;box-shadow:0 2px 8px #0009;backdrop-filter:blur(1px)}}
              iframe{{position:absolute;inset:0;width:500px;height:300px}}
              </style><main class="shell"><div class="player-main">
              <iframe id="movie" src="http://localhost:{self.server.server_port}/frame"></iframe>
              </div></main>'''.encode())
        elif self.path == '/frame':
            self.wfile.write(b'''<!doctype html><style>html,body{margin:0;height:100%}button{width:100%;height:100%}</style>
              <button id="play">Play / pause</button><script>
                window.hits=0;window.identity=crypto.randomUUID();
                document.querySelector('button').addEventListener('pointerdown',()=>window.hits++);
                document.querySelector('button').addEventListener('click',()=>window.hits++);
              </script>''')
        else:
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
            page.goto(url + 'embedded')
            frame = page.frame_locator('#movie')
            frame.get_by_role('button').wait_for()
            frame_id = page.frames[1].evaluate('window.identity')
            frame.get_by_role('button').focus()
            worker.evaluate('''async url => {
              const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');
            }''', url + 'embedded')
            page.keyboard.press('Escape')
            assert page.locator('html > div').count() == 0, 'Escape must cancel even if focus was inside an iframe'
            worker.evaluate('''async url => {
              const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');
            }''', url + 'embedded')
            bounds = page.locator('#movie').bounding_box()
            page.mouse.move(bounds['x'] + 200, bounds['y'] + 120)
            page.mouse.click(bounds['x'] + 200, bounds['y'] + 120)
            page.wait_for_timeout(300)
            hits = page.frames[1].evaluate('window.hits')
            assert hits == 0, f'Selection must not trigger iframe player play/pause; got {hits} events'
            page.wait_for_function("document.querySelector('#movie').getAttributeNames().some(x=>x.endsWith('-target'))", timeout=3000)
            assert page.frames[1].evaluate('window.identity') == frame_id
            rect = page.locator('#movie').bounding_box()
            viewport = page.evaluate('({width:innerWidth,height:innerHeight})')
            assert abs(rect['x'] + rect['width'] / 2 - viewport['width'] / 2) < 1, 'Player must be centered on the window, not an ancestor'
            assert abs(rect['y'] + rect['height'] / 2 - viewport['height'] / 2) < 1, 'Player must not be shifted by ancestor layout'
            assert page.locator('.shell').evaluate('(e)=>e.getBoundingClientRect().height') == 0, 'Original site shell must not paint behind the player'
            assert page.locator('body').evaluate("(e)=>getComputedStyle(e,'::after').display") == 'none', 'Page decorations must disappear'
            assert page.locator('html').evaluate('(e)=>getComputedStyle(e).backgroundColor') == 'rgb(0, 0, 0)', 'Outside the selected player only a black background is allowed'
            page.screenshot(path=str(ROOT / 'tests' / 'iframe-selected.png'))
            worker.evaluate('''async url => {
              const [tab]=await chrome.tabs.query({url});await restore(tab.id);
            }''', url + 'embedded')
            frame.get_by_role('button').click()
            assert page.frames[1].evaluate('window.hits') == 2, 'Player controls must work normally after selection ends'
            assert page.locator('.shell').evaluate('(e)=>getComputedStyle(e).display') == 'block'
            assert page.locator('body').evaluate("(e)=>getComputedStyle(e,'::after').content") == '\"\"', 'Page decorations must return with the tab'
            worker.evaluate('''async url=>chrome.storage.local.remove(`selection:${url}`)''', url + 'embedded')
            print('PASS: cross-origin iframe selection intercepts pointerdown/click without reloading the player')
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
            box = page.locator('video').bounding_box()
            page.mouse.move(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
            page.wait_for_timeout(250)
            assert page.evaluate('window.playerEvents') == 0, 'Selection must intercept direct video pointerdown handlers'
            assert page.locator('video').evaluate('(v)=>!v.paused'), 'Selection must preserve playing state'
            command('restore')
            command('forget')
            page.locator('video').click()
            assert page.evaluate('window.playerEvents') == 1, 'Video pointer events must work again after returning'
            page.locator('video').evaluate('(v)=>v.play()')
            print('PASS: direct video selection preserves playback and restores pointer events')

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

            def control(label, function='function(){this.click()}'):
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
                result = cdp.send('Runtime.callFunctionOn', {'objectId': obj, 'functionDeclaration': function, 'returnByValue': True})
                return result['result'].get('value')

            def click_control(label):
                rect = control(label, '''function(){
                  const r=this.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};
                }''')
                page.mouse.move(rect['x'], rect['y'])
                page.mouse.click(rect['x'], rect['y'])

            panel = 'Управление отдельным окном'
            metrics = '''function(){
              const rect=this.getBoundingClientRect(), style=getComputedStyle(this);
              return {opacity:Number(style.opacity),x:rect.x,y:rect.y,width:rect.width,height:rect.height};
            }'''
            page.mouse.move(5, 345)
            page.wait_for_timeout(200)
            assert control(panel, metrics)['opacity'] == 0, 'Controls must disappear away from their hover area'
            rect = page.locator('#widget').bounding_box()
            assert abs(rect['y'] + rect['height'] / 2 - 175) < 1, 'Controls must not reserve space above the block'
            page.screenshot(path=str(ROOT / 'tests' / 'window-preview.png'))
            area = control(panel, metrics)
            page.mouse.move(area['x'] + area['width'] - 8, area['y'] + 8)
            page.wait_for_timeout(200)
            assert 0 < control(panel, metrics)['opacity'] < 1, 'Hovered controls must be translucent'
            page.screenshot(path=str(ROOT / 'tests' / 'controls-preview.png'))
            area = control(panel, metrics)
            assert area['x'] >= 0 and area['x'] + area['width'] <= 500
            page.mouse.move(5, 345)
            page.wait_for_timeout(200)
            assert control(panel, metrics)['opacity'] == 0
            control('Увеличить', 'function(){this.focus()}')
            page.wait_for_timeout(200)
            assert control(panel, metrics)['opacity'] > 0, 'Keyboard focus must reveal controls'
            page.keyboard.press('Escape')
            page.wait_for_timeout(200)
            assert control(panel, metrics)['opacity'] == 0
            print('PASS: hidden overlay, hover transparency, no reserved space, keyboard focus and Escape')

            click_control('Сохранить или забыть размер и положение окна')
            page.wait_for_timeout(200)
            assert state()['local'][f'selection:{url}']['bounds']['width'] > 0
            click_control('Сохранить или забыть размер и положение окна')
            page.wait_for_timeout(150)
            page.mouse.move(5, 345)
            page.wait_for_timeout(200)
            assert control(panel, metrics)['opacity'] == 0, 'Clicked controls must also hide when the pointer leaves'
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
            assert struct.unpack('>II', path.read_bytes()[16:24]) == (500, 300), 'Snapshot must include the full block without a toolbar crop'
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
            page.goto(link)
            page.wait_for_timeout(500)
            popup = next(w for w in state()['windows'] if w['type'] == 'popup')
            origin = next(iter(state()['session'].values()))['originWindowId']
            with context.expect_page(timeout=5000) as recovered:
                worker.evaluate('windowId=>chrome.windows.remove(windowId)', popup['id'])
            page = recovered.value
            page.wait_for_load_state()
            assert page.url == url, 'Closing the popup must recover its page as a regular tab'
            page.locator('header').wait_for(state='visible')
            page.wait_for_timeout(200)
            result = state()
            assert not result['session'], 'Recovery must clear the detached state'
            assert all(w['type'] == 'normal' for w in result['windows'])
            assert any(w['id'] == origin and any(t['url'] == url for t in w['tabs']) for w in result['windows'])
            assert len(context.pages) == 1, 'Recovery must replace the temporary blank tab'
            print('PASS: native popup close restores the page to its original normal window')
            page.goto(link)
            page.wait_for_timeout(500)
            page.goto(url + '?episode=next')
            page.wait_for_timeout(200)
            popup = next(w for w in state()['windows'] if w['type'] == 'popup')
            with context.expect_page(timeout=5000) as recovered:
                worker.evaluate('windowId=>chrome.windows.remove(windowId)', popup['id'])
            page = recovered.value
            page.wait_for_load_state()
            assert page.url == url + '?episode=next', 'Recovery must use the latest page URL'
            page.wait_for_timeout(200)
            assert not state()['session']
            assert len(context.pages) == 1
            assert not errors, errors
            print('PASS: native popup close recovers the latest navigated URL without reopening the popup')
            page.screenshot(path=str(ROOT / 'tests' / 'verified-page.png'))
            print('ALL SMOKE CHECKS PASSED')
        except Exception:
            if not page.is_closed():
                page.screenshot(path=str(ROOT / 'tests' / 'failure.png'))
            if 'state' in locals():
                print('Failure state:', json.dumps(state(), ensure_ascii=True), flush=True)
            raise
        finally:
            context.close()
            server.shutdown()


if __name__ == '__main__':
    main()
