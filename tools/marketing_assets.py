"""Capture actual extension behavior and compose benefit-led RU/EN store galleries."""
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
  ('Your content.<br>Its own window.','Pick a page element. Give it room to breathe.'),
  ('Just the video.<br>Nothing in the way.','Hide player panels. Bring them back whenever you need them.'),
  ('Keep watching.<br>Keep working.','Float your video above other apps with picture-in-picture.')],
 'ru':[
  ('Нужный блок.<br>Отдельное окно.','Выбери часть страницы. Освободи место для главного.'),
  ('Только видео.<br>Без лишнего.','Скрой панели плеера. Верни настройки, когда понадобятся.'),
  ('Смотри, пока<br>работаешь.','Видео поверх других приложений в режиме «картинка в картинке».')]
}


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args): pass


def uri(path): return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()


def capture(context,worker,port,lang):
    worker.evaluate('lang=>chrome.storage.local.set({language:lang})',lang)
    page=context.new_page()
    page.goto(f'http://127.0.0.1:{port}/marketing-demo.html?lang={lang}')
    page.wait_for_function('document.querySelector("video").currentTime>0')
    page.mouse.move(600,670)
    page.locator('#player').screenshot(path=str(ART/f'before-{lang}.png'))
    url=page.url
    worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}''',url)
    rect=page.locator('video').bounding_box()
    page.mouse.move(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
    page.mouse.wheel(0,100)
    page.screenshot(path=str(ART/f'source-{lang}.png'))
    page.mouse.click(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
    page.wait_for_function('getComputedStyle(document.querySelector(".player-ui")).display==="none"')
    page.set_viewport_size({'width':1280,'height':800})
    page.mouse.move(10,400)
    page.wait_for_timeout(150)
    assert not page.locator('video').evaluate('(v)=>v.controls')
    page.locator('#player').screenshot(path=str(ART/f'clean-{lang}.png'))
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


def render(context,lang):
    page=context.new_page();page.set_viewport_size({'width':1280,'height':800})
    before='До' if lang=='ru' else 'Before'
    after='После' if lang=='ru' else 'After'
    demo='Демонстрационные данные' if lang=='ru' else 'Demo content'
    pip='Картинка в картинке' if lang=='ru' else 'Picture-in-picture'
    brand=uri(ROOT/'icons/icon128.png')
    source=uri(ART/f'source-{lang}.png');clean=uri(ART/f'clean-{lang}.png');original=uri(ART/f'before-{lang}.png')
    for index,(title,subtitle) in enumerate(COPY[lang],1):
        common=f'''<style>*{{box-sizing:border-box}}body{{margin:0;width:1280px;height:800px;overflow:hidden;font-family:"Segoe UI",sans-serif;background:#2357d9;color:white}}
        header{{position:absolute;left:64px;top:42px;display:flex;align-items:center;gap:10px;font-size:20px;font-weight:650}}header img{{width:48px;height:48px}}
        h1{{position:absolute;left:64px;top:132px;margin:0;font-size:76px;font-weight:650;letter-spacing:-2.8px;line-height:1.03}}.sub{{position:absolute;left:68px;top:310px;margin:0;font-size:20px;line-height:1.5;max-width:1120px;color:#dce6ff}}
        .frame{{position:absolute;overflow:hidden;border-radius:12px;background:#fff;box-shadow:0 20px 48px #05143140;line-height:0}}.frame>img{{width:100%;display:block}}.chrome{{height:28px;background:#f6f8fc;border-bottom:1px solid #dde4ee;display:flex;align-items:center;gap:5px;padding:0 12px}}.chrome i{{width:6px;height:6px;border-radius:50%;background:#9caec7}}
        .note{{position:absolute;bottom:22px;left:68px;font-size:11px;color:#c4d4ff}}.tag{{position:absolute;font-size:16px;font-weight:600}}
        </style><header><img src="{brand}" alt="">Separate Window</header><h1>{title}</h1><p class="sub">{subtitle}</p>'''
        chrome='<div class="chrome"><i></i><i></i><i></i></div>'
        if index==1:
            scene=f'''<style>.source{{left:64px;top:406px;width:750px;opacity:.85}}.result{{left:690px;top:372px;width:526px;border:2px solid #fff}}.arrow{{position:absolute;left:619px;top:374px;font-size:68px;color:#c5d8ff;line-height:1}}</style>
            <div class="frame source">{chrome}<img src="{source}"></div><div class="arrow">↗</div><div class="frame result">{chrome}<img src="{clean}"></div>'''
        elif index==2:
            scene=f'''<style>body{{background:#101b2d}}h1{{font-size:72px}}.sub{{color:#b8c7dd}}.before{{left:64px;top:412px;width:550px}}.after{{left:666px;top:412px;width:550px;border:2px solid #8caeff}}.tag{{top:369px}}.transition{{position:absolute;left:625px;top:555px;color:#87aaff;font-size:34px}}</style>
            <span class="tag" style="left:68px;color:#b8c7dd">{before}</span><span class="tag" style="left:670px;color:#a7c4ff">{after}</span>
            <div class="frame before"><img src="{original}"></div><div class="transition">→</div><div class="frame after"><img src="{clean}"></div>'''
        else:
            heading='Заметки к съёмке' if lang=='ru' else 'Workshop notes'
            document='Свет у воды' if lang=='ru' else 'Light by the water'
            text='Мягкий свет. Спокойная вода. Отражения связывают передний и дальний планы.' if lang=='ru' else 'Soft light. Still water. Reflections connect the foreground to the distant shore.'
            task1='Найти точку съёмки' if lang=='ru' else 'Choose a viewpoint'
            task2='Проверить экспозицию' if lang=='ru' else 'Check the exposure'
            task3='Снять серию кадров' if lang=='ru' else 'Capture a sequence'
            scene=f'''<style>body{{background:#e9f0ff;color:#172b4c}}.sub{{color:#526784}}.workspace{{left:64px;top:392px;width:1152px;height:346px;background:white;line-height:1.5;color:#334a67;box-shadow:0 12px 38px #13386a20}}
            .workspace nav{{height:48px;border-bottom:1px solid #e4eaf3;padding:12px 24px;font-size:16px;font-weight:600}}.editor{{padding:28px 34px;width:660px}}.editor h2{{font-size:26px;margin:0 0 14px;letter-spacing:-.6px}}.editor p{{font-size:17px;line-height:1.6;margin:0 0 18px}}.editor li{{font-size:16px;margin:7px 0;list-style:none}}.editor ul{{padding:0}}.editor li:before{{content:'□';margin-right:12px;color:#6483b5}}
            .pip{{left:823px;top:462px;width:365px;background:#000;border:2px solid #344963;box-shadow:0 20px 35px #152c5145}}.tag{{left:827px;top:424px;color:#2357d9;font-size:15px}}.note{{color:#647b9b}}
            </style><div class="frame workspace"><nav>{heading}</nav><article class="editor" contenteditable="true"><h2>{document}</h2><p>{text}</p><ul><li>{task1}</li><li>{task2}</li><li>{task3}</li></ul></article></div>
            <span class="tag">{pip}</span><div class="frame pip"><img src="{clean}"></div>'''
        page.set_content('<!doctype html><meta charset="utf-8">'+common+scene+f'<span class="note">{demo}</span>')
        page.locator('img').first.wait_for()
        page.evaluate('Promise.all([...document.images].map(img=>img.decode()))')
        output=OUT/f'screenshot-0{index}-{["select","window","app"][index-1]}-{lang}.png'
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
                    render(context,lang)
                    print(f'Captured and rendered {lang} benefit-led gallery',flush=True)
            finally:context.close()
        names=['global-01-select.png','global-02-video.png','global-03-work.png']
        for index,name in enumerate(names,1):
            shutil.copy2(OUT/f'screenshot-0{index}-{["select","window","app"][index-1]}-en.png',OUT/name)
        stale=OUT/'global-03-languages.png'
        if stale.exists():stale.unlink()
        for path in list(OUT.glob('screenshot-*.png'))+list(OUT.glob('global-*.png')):
            with Image.open(path) as image:assert image.size==(1280,800) and image.mode=='RGB',path
        version=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['version']
        for kind,files in [('global',names),('localized-ru',[f'screenshot-0{i}-{k}-ru.png' for i,k in [(1,'select'),(2,'window'),(3,'app')]]),('localized-en',[f'screenshot-0{i}-{k}-en.png' for i,k in [(1,'select'),(2,'window'),(3,'app')]])]:
            archive_path=ROOT/f'dist/{kind}-screenshots-{version}.zip'
            archive_path.parent.mkdir(exist_ok=True)
            with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
                for name in files:archive.write(OUT/name,name)
        print('Verified 9 RGB PNG screenshots, 1280x800, and 3 upload ZIPs')
    finally:server.shutdown()


if __name__=='__main__':main()
