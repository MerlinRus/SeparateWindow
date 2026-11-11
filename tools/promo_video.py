"""Record real extension actions, then render a short English promotional film.
Dev dependency: pip install --target tools/.deps imageio-ffmpeg
"""
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/'tools/.artifacts/promo'
VERSION=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))['version']
sys.path.insert(0,str(ROOT/'tools/.deps'))
import imageio_ffmpeg
from promo_music import add_music


class Handler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass


def uri(path):return 'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()


def record(context,worker,port,kind):
    # Screenshot capture follows the page across native window moves, unlike the
    # browser recorder, whose old render surface can become blank after detach.
    page=context.new_page()
    file='marketing-demo.html' if kind=='video' else 'calculator-demo.html'
    url=f'http://127.0.0.1:{port}/{file}?lang=en'
    page.goto(url)
    if kind=='video':page.wait_for_function('document.querySelector("video").currentTime>0')
    identity=page.evaluate('window.identity=window.identity||crypto.randomUUID()')
    page.mouse.move(16,16)
    fps=20;count=150 if kind=='video' else 145
    marks={'offset':0,'select':1,'click':3.1 if kind=='video' else 2.5,'duration':count/fps}
    output=ART/f'{kind}.webm'
    log=(ART/f'record-{kind}.log').open('wb')
    encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','image2pipe','-vcodec','png','-framerate',str(fps),'-i','-',
        '-an','-c:v','libvpx-vp9','-b:v','0','-crf','24',str(output)],stdin=subprocess.PIPE,stderr=log)
    try:
        for frame in range(count):
            if frame==20:
                worker.evaluate("""async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}""",url)
                box=page.locator('video' if kind=='video' else '#calculator').bounding_box()
                marks['point']=[box['x']+box['width']/2,box['y']+box['height']/2] if kind=='video' else [box['x']+12,box['y']+12]
            if frame==30:page.mouse.move(*marks['point'],steps=20)
            if frame==round(marks['click']*fps):
                page.mouse.click(*marks['point'])
                if kind=='video':page.wait_for_function('getComputedStyle(document.querySelector(".player-ui")).display==="none"')
                else:page.wait_for_function('document.querySelector("#calculator").getAttributeNames().some(n=>n.endsWith("-target"))')
                assert page.evaluate('window.identity')==identity
            if kind=='calculator' and frame==75:page.locator('#quantity').fill('2')
            if kind=='calculator' and frame==95:
                page.locator('#calculate').click()
                assert page.locator('#total').inner_text()=='500'
            png=page.screenshot(type='png')
            encoder.stdin.write(png)
        encoder.stdin.close();code=encoder.wait()
        if code:raise RuntimeError((ART/f'record-{kind}.log').read_text())
    finally:
        if encoder.poll() is None:encoder.kill()
        log.close();page.close()
    assert output.stat().st_size>10000
    return marks


def story(metadata):
    template=(ROOT/'tools/promo-story.html').read_text(encoding='utf-8')
    data={**metadata,'brand':uri(ROOT/'icons/icon128.png'),
          'overview':uri(ROOT/'tools/.artifacts/overview-en.png'),
          'menuHeader':uri(ROOT/'tools/.artifacts/popup-header-en.png'),
          'menuButton':uri(ROOT/'tools/.artifacts/popup-action-en.png')}
    path=ART/'story.html'
    path.write_text(template.replace('__PROMO_DATA__',json.dumps(data)),encoding='utf-8')
    return path


def main():
    ART.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT/'tools')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    encoder=None
    try:
        with tempfile.TemporaryDirectory(prefix='sw-promo-') as profile,sync_playwright() as p:
            if '--reuse-recordings' in sys.argv:
                cached=json.loads((ART/'metadata.json').read_text(encoding='utf-8'))
                metadata={kind:cached[kind] for kind in ('video','calculator')}
            else:
                context=p.chromium.launch_persistent_context(profile,channel='chromium',headless=True,
                    viewport={'width':1280,'height':640},
                    args=['--lang=en',f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'])
                try:
                    worker=context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                    worker.evaluate('chrome.storage.local.set({language:"en"})')
                    metadata={kind:record(context,worker,server.server_port,kind) for kind in ('video','calculator')}
                finally:context.close()
                print('Recorded real selection, isolation and calculator input without reload',flush=True)
            # Use explicitly decoded frames for deterministic browser composition.
            # Native paused-video seeks can leave the screenshot surface stale.
            (ART/'frames').mkdir(exist_ok=True)
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            for kind in ('video','calculator'):
                subprocess.run([ffmpeg,'-y','-loglevel','error','-i',str(ART/f'{kind}.webm'),
                    '-vf','fps=30',str(ART/'frames'/f'{kind}-%04d.png')],check=True)
            story(metadata)
            browser=p.chromium.launch(channel='chromium',headless=True)
            page=browser.new_page(viewport={'width':1280,'height':720},device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{server.server_port}/.artifacts/promo/story.html')
            page.wait_for_function('window.ready===true')
            duration=page.evaluate('window.duration')
            fps=30;frames=round(duration*fps)
            out=ROOT/f'dist/separate-window-global-promo-{VERSION}.mp4';out.parent.mkdir(exist_ok=True)
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            log=(ART/'encode.log').open('wb')
            encoder=subprocess.Popen([ffmpeg,'-y','-loglevel','error','-f','image2pipe','-vcodec','png','-framerate',str(fps),'-i','-',
                '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],stdin=subprocess.PIPE,stderr=log)
            samples={int(t*fps) for t in [1,5,10,14,duration-5,duration-1] if t<duration}
            for frame in range(frames):
                page.evaluate('(time)=>window.seek(time)',frame/fps)
                png=page.screenshot(type='png')
                encoder.stdin.write(png)
                if frame in samples:(ART/f'frame-{frame:04}.png').write_bytes(png)
                if frame%(fps*4)==0:print(f'Rendering {frame/fps:.0f}/{duration:.1f}s',flush=True)
            encoder.stdin.close();code=encoder.wait();log.close();browser.close()
            if code:raise RuntimeError((ART/'encode.log').read_text())
            assert out.stat().st_size>100000
            metadata.update({'duration':frames/fps,'fps':fps,'width':1280,'height':720,'file':out.name,'audio':False})
            (ART/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
            # Full decode catches incomplete files and broken packets.
            subprocess.run([ffmpeg,'-v','error','-i',str(out),'-f','null','-'],check=True)
            print(f'PASS: {out.name}, {frames/fps:.2f}s, 1280x720, 30fps, H.264; full decode passed; {out.stat().st_size} bytes',flush=True)
            music=add_music(out,frames/fps)
            metadata.update({'file':music.name,'audio':True})
            (ART/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    finally:
        if encoder and encoder.poll() is None:encoder.kill()
        server.shutdown()


if __name__=='__main__':main()
