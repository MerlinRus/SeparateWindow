"""Capture global CWS screenshots from the real extension on owned demo content."""
import base64
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import zipfile
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'docs/store/assets'
ART = ROOT/'tools/.artifacts'
ART.mkdir(exist_ok=True)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


def data_uri(path):
    return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()


def main():
    server = ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT/'tools')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='sw-global-') as profile, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(profile,channel='chromium',headless=True,
                locale='en-US',reduced_motion='reduce',viewport={'width':1280,'height':800},
                args=['--lang=en',f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'])
            try:
                worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                extension_id=worker.url.split('/')[2]
                page=context.pages[0]
                url=f'http://127.0.0.1:{server.server_port}/demo.html?lang=en'
                page.goto(url)
                page.wait_for_function('document.querySelector("video").currentTime>0')
                worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}''',url)
                rect=page.locator('#movie').bounding_box()
                point=(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
                page.mouse.move(*point)
                page.screenshot(path=str(OUT/'global-01-select.png'))
                page.mouse.click(*point)
                page.wait_for_function('document.querySelector("video").controls===false')
                page.set_viewport_size({'width':1280,'height':800})
                page.mouse.move(10,400)
                page.wait_for_timeout(200)
                page.screenshot(path=str(OUT/'global-02-video.png'))
                popup=context.new_page();popup.set_viewport_size({'width':376,'height':650})
                popup.goto(f'chrome-extension://{extension_id}/popup.html')
                popup.locator('#version').wait_for()
                for lang in ('en','ru'):
                    popup.locator('#language').select_option(lang)
                    popup.wait_for_function('(lang)=>document.documentElement.lang===lang',arg=lang)
                    popup.wait_for_function('!document.querySelector("#language").disabled')
                    popup.locator('body').screenshot(path=str(ART/f'global-popup-{lang}.png'))
                board=context.new_page();board.set_viewport_size({'width':1280,'height':800})
                board.set_content(f'''<!doctype html><style>
                *{{box-sizing:border-box}}body{{margin:0;background:#eef3fb;color:#192e4d;font-family:"Segoe UI",sans-serif}}
                header{{position:absolute;left:164px;top:48px;display:flex;align-items:center;gap:14px;font-size:25px;font-weight:650}}
                header img{{width:52px;height:52px}}.panel{{position:absolute;top:150px;border-radius:12px;overflow:hidden;box-shadow:0 14px 48px #16386a20;line-height:0}}
                .panel img{{width:376px;height:auto}}.en{{left:164px}}.ru{{right:164px}}
                </style><header><img src="{data_uri(ROOT/'icons/icon128.png')}" alt="">Separate Window</header>
                <div class="panel en"><img src="{data_uri(ART/'global-popup-en.png')}" alt=""></div>
                <div class="panel ru"><img src="{data_uri(ART/'global-popup-ru.png')}" alt=""></div>''')
                board.screenshot(path=str(OUT/'global-03-languages.png'))
            finally: context.close()
        paths=sorted(OUT.glob('global-*.png'))
        assert len(paths)==3
        for path in paths:
            with Image.open(path) as screenshot:
                assert screenshot.size==(1280,800)
                screenshot.convert('RGB').save(path)
            with Image.open(path) as screenshot: assert screenshot.mode=='RGB'
        version=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['version']
        archive_path=ROOT/f'dist/global-screenshots-{version}.zip'
        archive_path.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in paths: archive.write(path,path.name)
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None and len(archive.namelist())==3
        print(f'Verified 3 global screenshots: RGB PNG 1280x800; {archive_path.name}')
    finally: server.shutdown()


if __name__=='__main__':main()
