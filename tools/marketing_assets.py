"""Capture the real open/select/watch workflow for RU/EN store galleries.
Design process: unslop by Damir Sokolovsky (@heydamir), CC BY 4.0.
https://heydamir.design/unslop
"""
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import tempfile
import threading
import zipfile
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/store/assets'
ART=ROOT/'tools/.artifacts'
COPY={
 'en':[
  ('Open Separate Window','Click “Select a page element”'),
  ('Select a page element','Point to the player and click to open it in a separate window'),
  ('Watch in a separate window','Leave the surrounding banners and player panels behind'),
  ('More than video','Open calculators, tables, calendars and other page elements')],
 'ru':[
  ('Открой Separate Window','Нажми «Выбрать блок на странице»'),
  ('Выбери блок на странице','Наведись на плеер и нажми, чтобы вынести его в отдельное окно'),
  ('Смотри в отдельном окне','Баннеры и панели плеера остаются на странице'),
  ('Не только видео','Выноси калькуляторы, таблицы, календари и другие блоки страницы')]
}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass


def uri(path): return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()


def capture(context,worker,port,lang):
    worker.evaluate('lang=>chrome.storage.local.set({language:lang})',lang)
    page=context.new_page()
    page.set_viewport_size({'width':1280,'height':640})
    page.goto(f'http://127.0.0.1:{port}/marketing-demo.html?lang={lang}')
    page.wait_for_function('document.querySelector("video").currentTime>0')
    popup=context.new_page();popup.set_viewport_size({'width':376,'height':650})
    extension_id=worker.url.split('/')[2]
    popup.goto(f'chrome-extension://{extension_id}/popup.html')
    popup.locator('#version').wait_for()
    popup.wait_for_function('(lang)=>document.documentElement.lang===lang',arg=lang)
    popup.locator('header').screenshot(path=str(ART/f'popup-header-{lang}.png'))
    popup.locator('#select').screenshot(path=str(ART/f'popup-action-{lang}.png'))
    popup.close()
    page.bring_to_front()
    page.mouse.move(10,10)
    page.screenshot(path=str(ART/f'overview-{lang}.png'))
    page.mouse.move(600,670)
    page.locator('#player').screenshot(path=str(ART/f'before-{lang}.png'))
    url=page.url
    worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}''',url)
    rect=page.locator('video').bounding_box()
    page.mouse.move(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
    page.screenshot(path=str(ART/f'source-{lang}.png'))
    box=page.locator('#player').bounding_box()
    page.screenshot(path=str(ART/f'selected-{lang}.png'),clip={'x':box['x']-8,'y':box['y']-8,'width':box['width']+16,'height':min(page.evaluate('innerHeight')-box['y']+8,box['height']+72)})
    page.mouse.click(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
    page.wait_for_function('getComputedStyle(document.querySelector(".player-ui")).display==="none"')
    page.set_viewport_size({'width':1280,'height':800})
    page.mouse.move(10,400)
    page.wait_for_timeout(150)
    assert not page.locator('video').evaluate('(v)=>v.controls')
    page.locator('video').screenshot(path=str(ART/f'clean-{lang}.png'))
    # Exercise the real PiP action; the gallery uses its video frame in an illustrative workspace layout.
    cdp=context.new_cdp_session(page)
    title=worker.evaluate('SWI18n.t("pinTitle")')
    def find(node):
        attrs=node.get('attributes',[])
        if dict(zip(attrs[::2],attrs[1::2])).get('aria-label')==title:return node
        for child in node.get('children',[])+node.get('shadowRoots',[]):
            found=find(child)
            if found:return found
    node=find(cdp.send('DOM.getDocument',{'depth':-1,'pierce':True})['root'])
    assert node
    obj=cdp.send('DOM.resolveNode',{'nodeId':node['nodeId']})['object']['objectId']
    xy=cdp.send('Runtime.callFunctionOn',{'objectId':obj,'functionDeclaration':'function(){const r=this.getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]}','returnByValue':True})['result']['value']
    page.mouse.move(*xy);page.mouse.click(*xy)
    page.wait_for_function('!!document.pictureInPictureElement')
    page.evaluate('document.exitPictureInPicture()')
    page.close()


def capture_widget(context,worker,port,lang):
    page=context.new_page();page.set_viewport_size({'width':1280,'height':640})
    url=f'http://127.0.0.1:{port}/calculator-demo.html?lang={lang}'
    page.goto(url)
    identity=page.evaluate('window.identity')
    page.screenshot(path=str(ART/f'widget-source-{lang}.png'))
    worker.evaluate("""async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}""",url)
    box=page.locator('#calculator').bounding_box()
    page.mouse.move(box['x']+12,box['y']+12);page.mouse.click(box['x']+12,box['y']+12)
    page.wait_for_function('document.querySelector("#calculator").getAttributeNames().some(name=>name.endsWith("-target"))')
    assert page.evaluate('window.identity')==identity
    assert page.locator('aside').is_hidden()
    page.locator('#quantity').fill('2');page.locator('#calculate').click()
    assert page.locator('#total').inner_text()=='500'
    page.locator('#quantity').fill('4');page.locator('#calculate').click()
    assert page.locator('#total').inner_text()=='1000'
    page.mouse.move(10,10)
    page.locator('#calculator').screenshot(path=str(ART/f'widget-{lang}.png'))
    page.close()


def render(context,lang):
    page=context.new_page();page.set_viewport_size({'width':1280,'height':800})
    brand=uri(ROOT/'icons/icon128.png')
    source=uri(ART/f'overview-{lang}.png')
    selected=uri(ART/f'source-{lang}.png')
    widget_source=uri(ART/f'widget-source-{lang}.png')
    widget=uri(ART/f'widget-{lang}.png')
    clean=uri(ART/f'clean-{lang}.png')
    popup_header=uri(ART/f'popup-header-{lang}.png')
    popup_action=uri(ART/f'popup-action-{lang}.png')
    labels=['Открой','Выбери','Смотри','Другие блоки'] if lang=='ru' else ['Open','Select','Watch','Other content']
    for index,(title,subtitle) in enumerate(COPY[lang],1):
        steps=''.join(f'<span class="step {"active" if i==index else ""}"><b>{i}</b>{label}</span>' for i,label in enumerate(labels,1))
        common=f'''<style>
        *{{box-sizing:border-box}}body{{margin:0;width:1280px;height:800px;overflow:hidden;font-family:"Segoe UI",sans-serif;background:#f5f6f8;color:#202731}}
        header{{position:absolute;left:64px;top:42px;display:flex;align-items:center;gap:10px;font-size:20px;font-weight:650}}header img{{width:48px;height:48px}}
        .steps{{position:absolute;right:64px;top:56px;display:flex;gap:24px;font-size:16px;color:#737d8b}}.step{{display:flex;gap:8px;align-items:center}}.step b{{font-weight:500;font-variant-numeric:tabular-nums}}.step.active{{color:#2357d9}}
        h1{{position:absolute;left:64px;top:140px;margin:0;font-size:52px;font-weight:500;letter-spacing:-1px;line-height:1.16}}
        .sub{{position:absolute;left:64px;top:212px;margin:0;font-size:20px;line-height:1.5;max-width:1152px;color:#596372}}
        .frame{{position:absolute;overflow:hidden;border-radius:12px;background:#fff;border:1px solid #dce0e5;box-shadow:0 8px 24px #0000000f;line-height:0}}.frame img{{width:100%;display:block}}
        .source{{left:64px;top:288px;width:752px;opacity:.64}}
        .popup{{left:736px;top:416px;width:480px;padding:24px}}.popup img+img{{margin-top:24px}}
        .selected,.result{{left:244px;top:288px;width:792px}}
        .selected{{left:160px;width:960px;border:0;background:transparent;border-radius:0;box-shadow:none}}
        .widget-result{{left:832px;top:288px;width:360px}}.cursor{{position:absolute;left:492px;top:548px;width:32px;height:40px}}
        .launch-cursor{{position:absolute;width:40px;height:50px;pointer-events:none}}
        </style><header><img src="{brand}" alt="">Separate Window</header><div class="steps">{steps}</div><h1>{title}</h1><p class="sub">{subtitle}</p>'''
        if index==1:
            scene=f'''<div class="frame source"><img src="{source}"></div><div class="frame popup"><img src="{popup_header}"><img src="{popup_action}"></div><svg class="launch-cursor" viewBox="0 0 32 40" aria-hidden="true"><path d="M3 2v29l8-7 7 13 6-3-7-13h11Z" fill="#202731" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>'''
        elif index==2:
            scene=f'''<div class="frame selected"><img src="{selected}"></div><svg class="cursor" viewBox="0 0 32 40"><path d="M3 2v29l8-7 7 13 6-3-7-13h11Z" fill="#202731" stroke="white" stroke-width="2" stroke-linejoin="round"/></svg>'''
        elif index==3:
            scene=f'<div class="frame result"><img src="{clean}"></div>'
        else:
            scene=f'<div class="frame source"><img src="{widget_source}"></div><div class="frame widget-result"><img src="{widget}"></div>'
        page.set_content('<!doctype html><meta charset="utf-8">'+common+scene)
        page.evaluate('Promise.all([...document.images].map(img=>img.decode()))')
        if index==1:
            button=page.locator('.popup img:last-child').bounding_box()
            cursor={'x':button['x']+button['width']-48,'y':button['y']+button['height']*.55}
            page.locator('.launch-cursor').evaluate('(element,point)=>{element.style.left=point.x+"px";element.style.top=point.y+"px"}',cursor)
            assert button['x'] < cursor['x']+4 < button['x']+button['width']
            assert button['y'] < cursor['y']+3 < button['y']+button['height']
        # No cropping or overlap in the instructional headings, including translated variants.
        assert page.locator('h1').evaluate('(e)=>e.getBoundingClientRect().right<=1216')
        assert page.locator('.sub').evaluate('(e)=>e.getBoundingClientRect().bottom<=264')
        output=OUT/f'screenshot-0{index}-{["select","window","app","widget"][index-1]}-{lang}.png'
        page.screenshot(path=str(output))
        with Image.open(output) as image:image.convert('RGB').save(output)
    page.close()


def main():
    ART.mkdir(exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT/'tools')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='sw-marketing-') as profile,sync_playwright() as p:
            context=p.chromium.launch_persistent_context(profile,channel='chromium',headless=True,viewport={'width':1280,'height':800},reduced_motion='reduce',args=['--lang=en',f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'])
            try:
                worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                for lang in ('en','ru'):
                    capture(context,worker,server.server_port,lang)
                    capture_widget(context,worker,server.server_port,lang)
                    render(context,lang)
                    print(f'Captured and rendered {lang} step-by-step gallery',flush=True)
            finally:context.close()
        names=['global-01-select.png','global-02-video.png','global-03-window.png','global-04-widget.png']
        for index,name in enumerate(names,1):
            shutil.copy2(OUT/f'screenshot-0{index}-{["select","window","app","widget"][index-1]}-en.png',OUT/name)
        for name in ['global-03-languages.png','global-03-work.png']:
            stale=OUT/name
            if stale.exists():stale.unlink()
        for path in list(OUT.glob('screenshot-*.png'))+list(OUT.glob('global-*.png')):
            with Image.open(path) as image:assert image.size==(1280,800) and image.mode=='RGB',path
        version=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['version']
        for kind,files in [('global',names),('localized-ru',[f'screenshot-0{i}-{k}-ru.png' for i,k in [(1,'select'),(2,'window'),(3,'app'),(4,'widget')]]),('localized-en',[f'screenshot-0{i}-{k}-en.png' for i,k in [(1,'select'),(2,'window'),(3,'app'),(4,'widget')]])]:
            archive_path=ROOT/f'dist/{kind}-screenshots-{version}.zip'
            archive_path.parent.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
                for name in files:archive.write(OUT/name,name)
        print('Verified 12 RGB PNG screenshots, 1280x800, and 3 upload ZIPs')
    finally:server.shutdown()


if __name__=='__main__':main()
