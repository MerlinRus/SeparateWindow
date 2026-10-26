"""Capture actual RU/EN UI on owned demo content; generate exact CWS image sizes."""
import base64
import json
from pathlib import Path
import shutil
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/store/assets'
OUT.mkdir(parents=True, exist_ok=True)
ART = ROOT / 'tools/.artifacts'
ART.mkdir(exist_ok=True)

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT / 'tools')))
threading.Thread(target=server.serve_forever, daemon=True).start()

def data_uri(path):
    return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()

def rgb(path):
    with Image.open(path) as image:
        image.convert('RGB').save(path)

try:
    with sync_playwright() as p:
        for language in ('ru','en'):
            with tempfile.TemporaryDirectory(prefix='sw-store-') as profile:
                context = p.chromium.launch_persistent_context(profile, channel='chromium', headless=True,
                    locale=f'{language}-' + ('RU' if language == 'ru' else 'US'), reduced_motion='reduce',
                    viewport={'width':1280,'height':800},
                    args=[f'--lang={language}',f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'])
                try:
                    worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                    actual = worker.evaluate('chrome.i18n.getUILanguage()')
                    print(f'{language}: browser UI locale {actual}', flush=True)
                    assert actual.startswith(language), f'Browser locale must match screenshot language: {actual}'
                    extension_id = worker.url.split('/')[2]
                    popup = context.new_page()
                    popup.set_viewport_size({'width':376,'height':650})
                    popup.goto(f'chrome-extension://{extension_id}/popup.html')
                    popup.locator('#version').wait_for()
                    assert not popup.locator('#select').text_content().strip() == '↗'
                    assert popup.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    popup_path = ART / f'popup-{language}.png'
                    popup.locator('body').screenshot(path=str(popup_path))
                    page = context.pages[0]
                    url = f'http://127.0.0.1:{server.server_port}/demo.html?lang={language}'
                    page.goto(url)
                    page.wait_for_function("document.querySelector('video').currentTime>0")
                    page.bring_to_front()
                    worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select')}''', url)
                    box = page.locator('#movie').bounding_box()
                    x,y = box['x'] + box['width']/2, box['y'] + box['height']/2
                    page.mouse.move(x,y)
                    page.screenshot(path=str(OUT / f'screenshot-01-select-{language}.png'))
                    page.mouse.click(x,y)
                    page.wait_for_timeout(250)
                    page.set_viewport_size({'width':1280,'height':800})
                    page.mouse.move(1260,16)
                    page.wait_for_timeout(150)
                    page.screenshot(path=str(OUT / f'screenshot-02-window-{language}.png'))
                    worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await restore(tab.id)}''', url)
                    board = context.new_page()
                    board.set_viewport_size({'width':1280,'height':800})
                    title = 'Главное — в своём окне' if language == 'ru' else 'Give it a window of its own'
                    body = 'Видео, виджеты, игры и другие блоки страницы.<br>Выберите нужное. Остальное не мешает.' if language == 'ru' else 'Videos, widgets, games and other page elements.<br>Pick what matters. Leave the clutter behind.'
                    note = 'Реальный интерфейс расширения · Демонстрационные данные' if language == 'ru' else 'Actual extension interface · Demo content'
                    board.set_content(f'''<!doctype html><style>*{{box-sizing:border-box}}body{{margin:0;background:#eef3fb;color:#192e4d;font-family:"Segoe UI",sans-serif}}.brand{{position:absolute;left:68px;top:64px;display:flex;align-items:center;gap:10px;font-size:19px;font-weight:650}}.brand img{{width:52px;height:52px}}h1{{position:absolute;left:76px;top:218px;width:610px;font-size:60px;line-height:1.07;letter-spacing:-2px;margin:0}}p{{position:absolute;left:80px;top:432px;font-size:20px;line-height:1.65;color:#516985}}.popup{{position:absolute;right:88px;top:120px;box-shadow:0 20px 60px #16386a24;border-radius:12px;overflow:hidden;line-height:0}}.popup img{{width:376px}}small{{position:absolute;left:80px;bottom:64px;color:#5e7592;font-size:12px}}</style><div class="brand"><img src="{data_uri(ROOT/'icons/icon128.png')}">Separate Window</div><h1>{title}</h1><p>{body}</p><div class="popup"><img src="{data_uri(popup_path)}"></div><small>{note}</small>''')
                    board.screenshot(path=str(OUT / f'screenshot-03-app-{language}.png'))
                finally:
                    context.close()
        browser = p.chromium.launch(channel='chromium', headless=True)
        page = browser.new_page()
        for width,height in ((440,280),(1400,560)):
            page.set_viewport_size({'width':width,'height':height})
            page.set_content(f'''<!doctype html><style>*{{box-sizing:border-box}}body{{margin:0;width:100vw;height:100vh;background:#2357d9;overflow:hidden}}.window{{position:absolute;border:solid rgba(255,255,255,.88);border-width:clamp(3px,.8vw,9px);border-radius:clamp(10px,3vw,30px)}}.back{{left:12%;top:21%;width:53%;height:60%;background:#1c49b8}}.front{{right:9%;top:13%;width:42%;height:59%;background:#e9f0ff;box-shadow:0 14px 0 #133b9c4d}}.front:before{{content:"";position:absolute;left:0;right:0;top:14%;border-top:clamp(2px,.4vw,5px) solid #2357d94a}}.front:after{{content:"↗";position:absolute;inset:0;display:grid;place-items:center;color:#2357d9;font:bold clamp(100px,24vw,260px)/1 "Segoe UI",sans-serif}}.dot{{position:absolute;width:6%;aspect-ratio:1;top:5%;left:5%;border-radius:50%;background:#7e9fe9}}.line{{position:absolute;left:8%;top:34%;width:48%;height:5%;background:#6e91e9}}.line:after{{content:"";position:absolute;top:240%;left:0;width:72%;height:100%;background:#507ae0}}</style><div class="window back"><i class="dot"></i><i class="line"></i></div><div class="window front"></div>''')
            page.screenshot(path=str(OUT / f'promo-{width}x{height}.png'))
        browser.close()
    for path in OUT.glob('*.png'):
        rgb(path)
    shutil.copy2(ROOT / 'icons/icon128.png', OUT / 'icon128.png')
    shutil.copy2(ROOT / 'icons/favicon.ico', ROOT / 'docs/favicon.ico')
    print('Store assets generated: 6 screenshots, 2 promos, icon128')
finally:
    server.shutdown()
