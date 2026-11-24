// Worker failure and ordering tests without changing an installed Chrome profile.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const workerSource = fs.readFileSync(path.join(__dirname, '..', 'background.js'), 'utf8');
const url = 'https://example.test/watch?item=1';
const extension = 'chrome-extension://test/';

function worker({incognito = false} = {}) {
  const tabs = new Map([[1, {id: 1, windowId: 10, index: 0, url, incognito, pinned: true}]]);
  const writes = [];
  const messages = [];
  const warnings = [];
  let tabId = 2;
  const signal = () => ({listener: null, addListener(listener) {this.listener = listener;}});
  function store(name) {
    const records = {};
    return {
      records,
      async get(key) {return structuredClone(key in records ? {[key]: records[key]} : {});},
      async set(values) {writes.push({name, values}); Object.assign(records, structuredClone(values));},
      async remove(key) {delete records[key];}
    };
  }
  const session = store('session'), local = store('local');
  const normal = {id: 10, type: 'normal', incognito};
  const popup = {id: 20, type: 'popup', incognito};
  const chrome = {
    storage: {session, local},
    runtime: {id: 'test', getURL: (name = '') => extension + name, onMessage: signal(), onInstalled: signal()},
    commands: {onCommand: signal()},
    contextMenus: {onClicked: signal(), removeAll: callback => callback(), create() {}},
    scripting: {executeScript: async () => []},
    tabs: {
      onUpdated: signal(), onAttached: signal(), onRemoved: signal(),
      async get(id) {if (!tabs.has(id)) throw new Error('Closed'); return {...tabs.get(id)};},
      async query(options) {return [...tabs.values()].filter(t => !options.windowId || t.windowId === options.windowId);},
      async create(options) {const tab = {id: tabId++, incognito, ...options}; tabs.set(tab.id, tab); return tab;},
      async remove(id) {tabs.delete(id);},
      async update(id, options) {Object.assign(tabs.get(id), options);},
      async move(id, {windowId}) {tabs.get(id).windowId = windowId;},
      async sendMessage(id, {type}) {messages.push([id,type]); return {ok:true};}
    },
    windows: {
      async get(id) {return id === normal.id ? normal : popup;},
      async getAll() {return [normal];},
      async create(options) {
        assert.equal(options.incognito, incognito);
        tabs.get(options.tabId).windowId = popup.id;
        return popup;
      },
      async update() {}
    }
  };
  const context = vm.createContext({
    chrome, URL, importScripts() {}, resetDetachedMedia() {},
    console: {error: error => warnings.push(error)},
    SWI18n: {t: key => key, ready: Promise.resolve(), onChange() {}}
  });
  vm.runInContext(workerSource, context);
  const content = {tab: tabs.get(1), url, frameId: 0};
  const send = (type, extra) => context.handle({type, ...extra}, content);
  const popupCommand = (type, extra) => context.handle({type, tabId: 1, ...extra}, {url: extension + 'popup.html'});
  const idle = () => vm.runInContext('inTabOrder(1, () => {})', context);
  return {chrome, tabs, writes, session, local, messages, warnings, send, popupCommand, idle, context};
}

(async () => {
  {
    const run = worker({incognito: true});
    run.local.records['selection:'+url] = {selector:'#normal'};
    await run.send('detach', {selector: '#video'});
    assert.equal(run.session.records['window:1'].incognito, true);
    assert.equal((await run.send('window-state')).incognito, true);
    await assert.rejects(run.send('bounds'), /privateBounds/);
    assert.equal(run.writes.some(write => write.name === 'local'), false);
    assert.deepEqual(run.local.records['selection:'+url], {selector:'#normal'});
    await run.send('restore');
    assert.equal(Object.keys(run.session.records).length, 0);
    assert.equal(run.tabs.get(1).windowId, 10);
    assert.equal(run.tabs.get(1).pinned, true);
  }
  {
    const run = worker();
    run.chrome.storage.local.set = async () => {throw new Error('Quota');};
    await run.send('detach', {selector: '#video'});
    assert.equal(run.tabs.get(1).windowId, 20);
    assert.match(String(run.warnings[0]), /Quota/);
    run.chrome.tabs.move = async () => {throw new Error('Move failed');};
    await assert.rejects(run.send('restore'), /Move failed/);
    assert.equal(run.tabs.get(1).windowId, 20);
    assert(run.session.records['window:1']);
    assert.equal(run.messages.some(([,type]) => type === 'uncrop'), false);
  }
  {
    const run = worker();
    const originalCreate = run.chrome.windows.create;
    run.chrome.windows.create = async options => {
      const popup = await originalCreate(options);
      run.tabs.delete(1);
      run.chrome.tabs.onRemoved.listener(1, {windowId:popup.id,isWindowClosing:true});
      return popup;
    };
    await run.send('detach', {selector: '#video'});
    await run.idle();
    assert.equal(Object.keys(run.session.records).length, 0);
    assert.deepEqual([...run.tabs.values()].map(tab => [tab.windowId,tab.url,tab.pinned]), [[10,url,true]]);
  }
  {
    const run = worker();
    await run.send('detach', {selector: '#video'});
    const placeholderId = run.session.records['window:1'].placeholderId;
    run.tabs.get(placeholderId).pendingUrl = 'https://example.test/new-task';
    run.chrome.contextMenus.onClicked.listener({menuItemId:'select'}, run.tabs.get(1));
    await run.idle();
    assert.equal(run.tabs.get(1).windowId, 10);
    assert(run.tabs.has(placeholderId), 'Keep a placeholder the user has already started navigating');
    assert.equal(Object.keys(run.session.records).length, 0);
  }
  {
    const run = worker();
    const sendShortcut = () => run.chrome.commands.onCommand.listener('select', run.tabs.get(1));
    await sendShortcut();
    await run.idle();
    assert.deepEqual(run.messages, [[1, 'select']]);
    await run.send('detach', {selector: '#video'});
    assert.equal(run.tabs.get(1).windowId, 20);
    await sendShortcut();
    await run.idle();
    assert.equal(run.tabs.get(1).windowId, 10);
    assert.equal(Object.keys(run.session.records).length, 0);
  }
  {
    const run = worker();
    await run.send('detach', {selector: '#video'});
    let active = run.tabs.get(1);
    run.chrome.tabs.query = async () => [active];
    run.chrome.tabs.captureVisibleTab = async () => {
      active = {id: 4, windowId: 20};
      return 'other tab';
    };
    await assert.rejects(run.send('capture'), /activePageRequired/);
  }
  {
    const run = worker();
    await run.chrome.runtime.onInstalled.listener({reason: 'update'});
    assert.equal(run.tabs.size, 1, 'Updates never show the welcome page');
    await run.chrome.runtime.onInstalled.listener({reason: 'install'});
    await run.chrome.runtime.onInstalled.listener({reason: 'install'});
    assert.equal(run.tabs.size, 2, 'Fresh install only opens one welcome tab');
    assert.equal(run.tabs.get(2).url, extension + 'welcome.html');
    assert.equal(run.local.records.onboarding, 'pending');
    await assert.rejects(run.send('onboarding', {choice: 'start'}), /commandFailed/);
    await run.popupCommand('onboarding', {choice: 'skip'});
    await run.popupCommand('onboarding', {choice: 'start'});
    assert.equal(run.local.records.onboarding, 'skipped');
    assert.equal(run.tabs.size, 2, 'A stale first-run prompt cannot open the tour after opt-out');
    await run.popupCommand('onboarding', {choice: 'replay'});
    assert.equal(run.tabs.get(3).url, 'https://separate.maark.ru/en/onboarding/');
  }
  {
    const run = worker(), origin = new URL(url).origin;
    const savedSelection = {selector: '#video', bounds: {left: 30, top: 40, width: 600, height: 400}};
    await run.local.set({[`selection:${url}`]: savedSelection});
    assert.equal((await run.popupCommand('auto-pip')).enabled, false);
    await assert.rejects(run.send('auto-pip', {enabled: true}), /commandFailed/);
    assert.equal((await run.popupCommand('auto-pip', {enabled: true})).enabled, true);
    assert.equal(run.local.records[`auto-pip:${origin}`], true);
    assert(run.messages.some(([,type]) => type === 'auto-pip-refresh'));
    run.tabs.get(1).url = origin + '/another-video';
    assert.equal((await run.popupCommand('auto-pip')).enabled, true);
    run.tabs.get(1).url = 'https://other.test/watch';
    assert.equal((await run.popupCommand('auto-pip')).enabled, false);
    run.tabs.get(1).url = url;
    assert.equal((await run.popupCommand('auto-pip', {enabled: false})).enabled, false);
    assert.equal(run.local.records[`auto-pip:${origin}`], undefined);
    assert.deepEqual(run.local.records[`selection:${url}`], savedSelection);
    const privateRun = worker({incognito: true});
    assert.equal((await privateRun.popupCommand('auto-pip', {enabled: true})).available, false);
    assert.equal(privateRun.writes.length, 0);
  }
  console.log('PASS: private storage, quota, failed moves, immediate close, context menu, shortcut return, capture tab switch, Auto PiP and onboarding lifecycle');
})().catch(error => {console.error(error); process.exitCode = 1;});
