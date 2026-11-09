"""Manual language overrides across popup, existing page UI and worker errors."""
import json
import tempfile
import threading
from http.server import ThreadingHTTPServer
from playwright.sync_api import sync_playwright
from smoke import Handler, ROOT


def main():
    dictionaries = {lang:json.loads((ROOT/f'_locales/{lang}/messages.json').read_text(encoding='utf-8')) for lang in ('ru','en')}
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='sw-languages-') as profile, sync_playwright() as p:
            context = p.chromium.launch_persistent_context(profile,channel='chromium',headless=True,
                args=['--lang=en',f'--disable-extensions-except={ROOT}',f'--load-extension={ROOT}'])
            try:
                worker = context.service_workers[0] if context.service_workers else context.wait_for_event('serviceworker')
                worker.evaluate('''async () => {
                  await SWI18n.ready;
                  const update=chrome.contextMenus.update.bind(chrome.contextMenus);
                  chrome.contextMenus.update=async (id,options)=>{await update(id,options);globalThis.menuTitle=options.title;};
                }''')
                popup_url = f'chrome-extension://{worker.url.split("/")[2]}/popup.html'
                popup = context.new_page(); popup.goto(popup_url)
                popup.locator('#version').wait_for()
                assert popup.locator('#language').input_value() == 'auto'
                browser_language = popup.locator('html').get_attribute('lang')
                def switch(lang):
                    popup.locator('#language').select_option(lang)
                    expected = browser_language if lang=='auto' else lang
                    popup.wait_for_function('(lang)=>document.documentElement.lang===lang',arg=expected)
                    popup.wait_for_function('!document.querySelector("#language").disabled')
                    assert popup.locator('#select').inner_text().strip().endswith(dictionaries[expected]['selectButton']['message'])
                    assert popup.locator('body').evaluate('(e)=>e.scrollWidth<=innerWidth')
                    worker.evaluate('''async title=>{for(let i=0;i<40;i++){if(globalThis.menuTitle===title)return;await new Promise(r=>setTimeout(r,50));}throw new Error('Context menu not translated');}''', dictionaries[expected]['contextMenu']['message'])
                page = context.pages[0]
                url = f'http://127.0.0.1:{server.server_port}/'
                page.goto(url)
                identity=page.evaluate('window.identity')
                worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await tell(tab.id,'select');}''',url)
                cdp=context.new_cdp_session(page)
                def labels():
                    tree=cdp.send('DOM.getDocument',{'depth':-1,'pierce':True})
                    def walk(node):
                        attrs=node.get('attributes',[]); pairs=dict(zip(attrs[::2],attrs[1::2]))
                        result=[pairs['aria-label']] if 'aria-label' in pairs else []
                        result += [node['nodeValue']] if node.get('nodeType')==3 else []
                        for child in node.get('children',[])+node.get('shadowRoots',[]):result+=walk(child)
                        return result
                    return walk(tree['root'])
                switch('ru')
                assert dictionaries['ru']['pickerHint']['message'] in labels()
                assert dictionaries['en']['pickerHint']['message'] not in labels()
                switch('en')
                assert dictionaries['en']['pickerHint']['message'] in labels()
                box=page.locator('#widget').bounding_box();page.mouse.click(box['x']+10,box['y']+10)
                page.wait_for_function('document.querySelector("header").getBoundingClientRect().height===0')
                switch('ru')
                assert dictionaries['ru']['returnTitle']['message'] in labels()
                assert dictionaries['en']['returnTitle']['message'] not in labels()
                assert page.evaluate('window.identity')==identity
                popup.reload();popup.locator('#version').wait_for()
                assert popup.locator('#language').input_value()=='ru'
                result=popup.evaluate('''async () => {
                  const [tab]=await chrome.tabs.query({url:'http://127.0.0.1/*'});
                  return chrome.runtime.sendMessage({type:'bad-command',tabId:tab.id});
                }''')
                assert result['error']==dictionaries['ru']['unknownCommand']['message']
                switch('en')
                assert dictionaries['en']['returnTitle']['message'] in labels()
                switch('auto')
                assert popup.locator('html').get_attribute('lang')==browser_language
                worker.evaluate('''async url=>{const [tab]=await chrome.tabs.query({url});await restore(tab.id);}''',url)
                assert page.evaluate('window.identity')==identity
                print('PASS: manual RU/EN, browser fallback, persisted selection, live picker/toolbar, context menu, worker errors, no reload')
            finally:context.close()
    finally:server.shutdown()


if __name__=='__main__':main()
