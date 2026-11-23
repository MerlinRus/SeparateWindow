"""A live dashboard panel must survive crop and its framework replacing it."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import io
import tempfile
import threading
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = b'''<!doctype html><style>
body{margin:0;background:#111;color:#bbc4d5;font:20px sans-serif}
header{height:80px}#dashboard{width:1100px;height:750px;transform:translateZ(0)}
#cell{width:600px;height:360px;margin:24px;container-type:inline-size}
#stat{width:100%;height:100%;box-sizing:border-box;background:#1e2736;padding:24px}
#value{color:#5794f2;font-size:100px}#outside{position:fixed;right:0;top:0;background:red}
</style><header>Dashboard</header><main id="dashboard"><div id="cell"><section id="stat">
<div>Processed</div><button id="value">1000</button></section></div></main>
<aside id="outside">Outside panel</aside><script>
window.identity=crypto.randomUUID();window.ticks=0;window.zeroSizes=0;
const cell=document.querySelector('#cell');
const original=document.querySelector('#stat').outerHTML;
function mount(){cell.innerHTML=original;document.querySelector('#value').onclick=()=>window.ticks++;}
mount();
new ResizeObserver(entries=>{
 const r=entries[0].contentRect;
 if(!r.width||!r.height){window.zeroSizes++;cell.replaceChildren();}
 else if(!document.querySelector('#stat'))mount();
}).observe(cell);
window.replacePanel=mount;
window.replaceContainer=()=>{document.querySelector('#cell').outerHTML='<div id="cell">'+original+'</div>';document.querySelector('#value').onclick=()=>window.ticks++;};
setInterval(()=>{const n=document.querySelector('#value');if(n)n.textContent=String(1000+window.ticks++);},100);
</script>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(FIXTURE)

    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}/'
    try:
        with tempfile.TemporaryDirectory(prefix='sw-dashboard-') as profile, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(profile, channel='chromium', headless=True,
                viewport={'width':1280,'height':900}, args=[f'--disable-extensions-except={ROOT}', f'--load-extension={ROOT}'])
            try:
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                page = context.pages[0]

                def select_panel(panel_url):
                    worker.evaluate("""async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}""", panel_url)
                    box = page.locator('#stat').bounding_box()
                    page.mouse.move(box['x']+8,box['y']+8)
                    page.mouse.click(box['x']+8,box['y']+8)
                    page.wait_for_function('''document.querySelector('#stat')?.getAttributeNames().some(name=>name.endsWith('-target'))''')

                def panel_background():
                    png = page.locator('#stat').screenshot()
                    return Image.open(io.BytesIO(png)).convert('RGB').getpixel((4,40))

                def assert_panel_background(expected, label):
                    actual = panel_background()
                    assert max(abs(a - b) for a, b in zip(actual, expected)) <= 1, (label, expected, actual)

                cases = [
                    ('white', 'body{background:white;color:black} #stat{background:transparent}', (255,255,255)),
                    ('layered', 'html{background:#284050} body{background:none} #cell{background:#80402080} #stat{background:transparent}', (84,64,56)),
                    ('default', 'body,#stat{background:transparent}', (255,255,255)),
                ]
                for name, css, expected in cases:
                    panel_url = url + '?background=' + name
                    page.goto(panel_url)
                    page.add_style_tag(content=css)
                    assert_panel_background(expected, name + ' in tab')
                    select_panel(panel_url)
                    assert_panel_background(expected, name + ' in separate window')
                    assert not page.locator('#outside').is_visible()
                    worker.evaluate('''async url => {
                      const [tab] = await chrome.tabs.query({url});
                      await handle({type:'restore', tabId:tab.id}, {url:chrome.runtime.getURL('popup.html')});
                    }''', panel_url)
                    page.locator('#outside').wait_for(state='visible')
                    assert_panel_background(expected, name + ' after restore')
                print('PASS: transparent blocks keep the white, tinted or default page background')

                page.goto(url)
                page.wait_for_function('window.ticks>1')
                identity = page.evaluate('window.identity')
                dimensions = page.locator('#cell').evaluate('(e)=>({w:e.clientWidth,h:e.clientHeight})')
                select_panel(url)
                page.wait_for_timeout(500)
                page.screenshot(path=str(ROOT/'tests/dashboard-selected.png'))
                assert page.locator('#stat').count()==1, f'BLACK WINDOW: panel unmounted; zero-size notifications={page.evaluate("window.zeroSizes")}'
                assert page.locator('#stat').is_visible(), 'BLACK WINDOW: selected panel hidden'
                assert page.evaluate('window.zeroSizes')==0, 'Crop must not collapse a measured dashboard container'
                assert page.locator('#cell').evaluate('(e)=>({w:e.clientWidth,h:e.clientHeight})')==dimensions
                before = page.evaluate('window.ticks')
                page.locator('#value').click()
                assert page.evaluate('window.ticks')>before
                page.set_viewport_size({'width':800,'height':620})
                page.wait_for_timeout(150)
                assert page.locator('#stat').is_visible()
                page.evaluate('window.replacePanel()')
                page.wait_for_timeout(150)
                assert page.locator('#stat').is_visible(), 'BLACK WINDOW: replacement panel lost crop attributes'
                assert page.locator('#stat').evaluate('(e)=>e.getAttributeNames().some(n=>n.endsWith("-target"))')
                page.locator('#value').click()
                page.evaluate('window.replaceContainer()')
                page.wait_for_timeout(150)
                assert page.locator('#cell').evaluate('(e)=>({w:e.clientWidth,h:e.clientHeight})')==dimensions, 'Replacement ancestors must be measured before crop hides them'
                page.locator('#value').click()
                assert page.evaluate('window.identity')==identity
                assert not page.locator('#outside').is_visible()
                assert not page.locator('header').is_visible()
                bounds = page.locator('#stat').bounding_box()
                assert abs(bounds['x']+bounds['width']/2-400)<2
                assert abs(bounds['y']+bounds['height']/2-310)<2
                assert_panel_background((30,39,54), 'dark panel after replacement')
                page.evaluate('''() => {
                  const slot = document.createElement('div');
                  slot.id = 'new-slot';
                  slot.style.cssText = 'width:600px;height:360px';
                  document.querySelector('main').append(slot);
                  slot.append(document.querySelector('#stat'));
                }''')
                page.locator('#stat').wait_for(state='visible', timeout=3000)
                assert page.locator('#new-slot').evaluate('(e)=>e.getAttributeNames().some(n=>n.endsWith("-ancestor"))')
                page.locator('#value').click()
                assert page.evaluate('window.identity')==identity
                page.locator('#stat').evaluate('(e)=>e.remove()')
                page.locator('header').wait_for(state='visible', timeout=6000)
                assert page.locator('#outside').is_visible(), 'A removed panel must not leave a black popup'
                worker.evaluate("""async url=>{const [tab]=await chrome.tabs.query({url});await restore(tab.id);}""", url)
                assert page.locator('header').is_visible() and page.locator('#outside').is_visible()
                assert page.locator('#cell').evaluate('(e)=>getComputedStyle(e).containerType')=='inline-size'
                assert not page.evaluate('''[...document.querySelectorAll('*')].some(
                    e => e.getAttributeNames().some(n => n.startsWith('data-sw-') && (n.endsWith('-target') || n.endsWith('-ancestor'))))''')
                print('PASS: live panel resize, replacement, reparenting and recovery after removal')
            finally:
                context.close()
    finally:
        server.shutdown()


if __name__=='__main__':
    main()
