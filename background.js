const t = (key, substitutions) => chrome.i18n.getMessage(key, substitutions);
const sessionKey = id => `window:${id}`;
const selectionKey = url => `selection:${url}`;
const supported = url => /^(https?|file):/.test(url || '');

async function tell(tabId, type) {
  try { return await chrome.tabs.sendMessage(tabId, {type}); }
  catch {
    const tab = await chrome.tabs.get(tabId);
    if (!supported(tab.url)) throw new Error(t('restrictedPage'));
    await chrome.scripting.executeScript({target: {tabId}, files: ['content.js']});
    return chrome.tabs.sendMessage(tabId, {type});
  }
}

async function findOrigin(state) {
  try {
    const origin = await chrome.windows.get(state.originWindowId);
    if (origin.type === 'normal' && origin.incognito === !!state.incognito) return origin;
  } catch {}
  return (await chrome.windows.getAll({windowTypes: ['normal']})).find(win => win.incognito === !!state.incognito);
}

async function removePlaceholder(state) {
  if (!state.placeholderId) return;
  try {
    const placeholder = await chrome.tabs.get(state.placeholderId);
    if (placeholder.url === 'about:blank') await chrome.tabs.remove(placeholder.id);
  } catch {}
}

async function restore(tabId) {
  const key = sessionKey(tabId);
  const state = (await chrome.storage.session.get(key))[key];
  await tell(tabId, 'uncrop').catch(() => {});
  if (!state) return;
  const origin = await findOrigin(state);
  if (origin) {
    await chrome.tabs.move(tabId, {windowId: origin.id, index: state.index});
    await chrome.tabs.update(tabId, {active: true});
    await chrome.windows.update(origin.id, {focused: true});
  } else {
    await chrome.windows.create({tabId, type: 'normal', incognito: !!state.incognito, focused: true});
  }
  await removePlaceholder(state);
  await chrome.storage.session.remove(key);
}

async function detach(tab, message) {
  const key = sessionKey(tab.id);
  if ((await chrome.storage.session.get(key))[key]) return;
  if (typeof message.selector !== 'string' || message.selector.length > 12000) throw new Error(t('invalidArea'));
  const pageUrl = tab.url.split('#__sw_local=')[0];
  const saved = (await chrome.storage.local.get(selectionKey(pageUrl)))[selectionKey(pageUrl)];
  const state = {originWindowId: tab.windowId, index: tab.index, url: pageUrl, incognito: tab.incognito, pinned: tab.pinned};
  const tabs = await chrome.tabs.query({windowId: tab.windowId});
  if (tabs.length === 1) state.placeholderId = (await chrome.tabs.create({windowId: tab.windowId, url: 'about:blank', active: false})).id;
  const bounds = saved?.bounds;
  const options = {tabId: tab.id, type: 'popup', focused: true,
    width: Math.max(320, Math.min(2400, Math.round(message.width || 800))),
    height: Math.max(240, Math.min(1600, Math.round((message.height || 500) + 40)))};
  if (bounds) Object.assign(options, bounds);
  try {
    const popup = await chrome.windows.create(options);
    state.popupWindowId = popup.id;
    await chrome.storage.session.set({[key]: state});
    await chrome.storage.local.set({[selectionKey(pageUrl)]: {...saved, selector: message.selector}});
  } catch (error) {
    await chrome.storage.session.set({[key]: state});
    await restore(tab.id);
    throw error;
  }
}

async function handle(message, sender) {
  // Content scripts may act only on their own tab; popup commands require an extension page.
  const extensionPage = !sender.tab && sender.url?.startsWith(chrome.runtime.getURL(''));
  const tabId = sender.tab?.id ?? (extensionPage ? message.tabId : undefined);
  if (!Number.isInteger(tabId)) throw new Error(t('noActiveTab'));
  const tab = await chrome.tabs.get(tabId);
  const key = sessionKey(tabId);
  const state = (await chrome.storage.session.get(key))[key];
  switch (message.type) {
    case 'select':
      if (state) return restore(tabId);
      return tell(tabId, 'select');
    case 'restore': return restore(tabId);
    case 'forget': return tell(tabId, 'forget');
    case 'detach':
      if (!sender.tab) throw new Error(t('selectFirst'));
      return detach(tab, message);
    case 'bounds': {
      if (!state) throw new Error(t('detachFirst'));
      const pageKey = selectionKey(tab.url);
      const saved = (await chrome.storage.local.get(pageKey))[pageKey] || {};
      const win = await chrome.windows.get(tab.windowId);
      const bounds = saved.bounds ? undefined : {left: win.left, top: win.top, width: win.width, height: win.height};
      if (bounds) saved.bounds = bounds;
      else delete saved.bounds;
      await chrome.storage.local.set({[pageKey]: saved});
      return {saved: !!bounds};
    }
    case 'bookmark': {
      if (!state || typeof message.url !== 'string') throw new Error(t('detachFirst'));
      const link = new URL(message.url);
      const source = new URL(tab.url);
      if (link.origin !== source.origin || link.pathname !== source.pathname || !supported(link.href)) throw new Error(t('invalidLink'));
      const folders = await chrome.bookmarks.search({title: 'Separate windows'});
      let folder = folders.find(item => !item.url);
      if (!folder) folder = await chrome.bookmarks.create({title: 'Separate windows'});
      await chrome.bookmarks.create({parentId: folder.id, title: tab.title || 'Separate Window', url: link.href});
      return;
    }
    case 'capture': {
      if (!state) throw new Error(t('noSeparateWindow'));
      const [active] = await chrome.tabs.query({active: true, windowId: tab.windowId});
      if (active?.id !== tabId) throw new Error(t('activePageRequired'));
      return {image: await chrome.tabs.captureVisibleTab(tab.windowId, {format: 'png'})};
    }
    default: throw new Error(t('unknownCommand'));
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  handle(message, sender).then(result => respond({ok: true, ...result}), error => respond({ok: false, error: error.message}));
  return true;
});
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => chrome.contextMenus.create({id: 'select', title: t('contextMenu'), contexts: ['all'], documentUrlPatterns: ['http://*/*', 'https://*/*', 'file:///*']}));
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'select') tell(tab.id, 'select').catch(console.error);
});
chrome.commands.onCommand.addListener(async command => {
  if (command !== 'select') return;
  const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
  if (tab) handle({type: 'select', tabId: tab.id}, {url: chrome.runtime.getURL('popup.html')}).catch(console.error);
});
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (!change.url) return;
  const key = sessionKey(tabId);
  chrome.storage.session.get(key).then(data => {
    if (data[key]) return chrome.storage.session.set({[key]: {...data[key], url: change.url.split('#__sw_local=')[0]}});
  }).catch(console.error);
});

async function recoverClosedPopup(tabId, info) {
  const key = sessionKey(tabId);
  const state = (await chrome.storage.session.get(key))[key];
  if (!state) return;
  // Native close has already destroyed the document. Recover the page, never an auto-open link.
  if (info.isWindowClosing && state.popupWindowId === info.windowId && supported(state.url)) {
    const origin = await findOrigin(state);
    if (origin) {
      await chrome.tabs.create({windowId: origin.id, index: state.index, url: state.url, active: true, pinned: !!state.pinned});
    } else {
      await chrome.windows.create({url: state.url, type: 'normal', incognito: !!state.incognito, focused: true});
    }
    await removePlaceholder(state);
  }
  await chrome.storage.session.remove(key);
}
chrome.tabs.onRemoved.addListener((tabId, info) => {
  recoverClosedPopup(tabId, info).catch(console.error);
});
