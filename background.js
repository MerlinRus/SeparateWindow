importScripts('i18n.js', 'media.js');
const t = (key, substitutions) => SWI18n.t(key, substitutions);
const sessionKey = id => `window:${id}`;
const selectionKey = url => `selection:${url}`;
const supported = url => /^(https?|file):/.test(url || '');
const pageAddress = url => url?.split('#__sw_local=')[0];
const tabJobs = new Map();
const preferenceJobs = new Map();

function samePageRoute(first, second) {
  if (!supported(first) || !supported(second)) return false;
  try {
    const a = new URL(first), b = new URL(second);
    return a.origin === b.origin && a.protocol === b.protocol && a.pathname === b.pathname;
  } catch {return false;}
}

function inOrder(jobs, key, task) {
  const result = (jobs.get(key) || Promise.resolve()).then(task);
  const tail = result.catch(() => {});
  jobs.set(key, tail);
  tail.then(() => {if (jobs.get(key) === tail) jobs.delete(key);});
  return result;
}
const inTabOrder = (tabId, task) => inOrder(tabJobs, tabId, task);
const inPreferenceOrder = (key, task) => inOrder(preferenceJobs, key, task);

async function tell(tabId, type) {
  let response;
  try {response = await chrome.tabs.sendMessage(tabId, {type}, {frameId: 0});}
  catch {
    const tab = await chrome.tabs.get(tabId);
    if (!supported(tab.url)) throw new Error(t('restrictedPage'));
    try {
      await chrome.scripting.executeScript({target: {tabId}, files: ['i18n.js', 'content.js']});
      response = await chrome.tabs.sendMessage(tabId, {type}, {frameId: 0});
    } catch {
      throw new Error(t('restrictedPage'));
    }
  }
  if (!response?.ok) throw new Error(response?.error || t('commandFailed'));
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
    if (placeholder.windowId === state.originWindowId && !placeholder.pinned &&
        (!placeholder.pendingUrl || placeholder.pendingUrl === 'about:blank') &&
        (placeholder.url === 'about:blank' || (!placeholder.url && placeholder.pendingUrl === 'about:blank'))) {
      await chrome.tabs.remove(placeholder.id);
    }
  } catch {}
}

async function moveToNormal(tabId, state) {
  const origin = await findOrigin(state);
  if (origin) {
    await chrome.tabs.move(tabId, {windowId: origin.id, index: state.index});
    await chrome.tabs.update(tabId, {active: true, pinned: !!state.pinned}).catch(() => {});
    await chrome.windows.update(origin.id, {focused: true}).catch(() => {});
  } else {
    await chrome.windows.create({tabId, type: 'normal', incognito: !!state.incognito, focused: true});
    if (state.pinned) await chrome.tabs.update(tabId, {pinned: true}).catch(() => {});
  }
}

async function finishRestore(tabId, state) {
  await chrome.scripting.executeScript({target: {tabId, allFrames: true}, func: resetDetachedMedia}).catch(() => {});
  await tell(tabId, 'uncrop').catch(() => {});
  if (state) {
    await removePlaceholder(state);
    await chrome.storage.session.remove(sessionKey(tabId));
  }
  await tell(tabId, 'returned').catch(() => {});
}

async function restore(tabId) {
  const key = sessionKey(tabId);
  const state = (await chrome.storage.session.get(key))[key];
  if (state && (await chrome.tabs.get(tabId)).windowId === state.popupWindowId) await moveToNormal(tabId, state);
  await finishRestore(tabId, state);
}

async function detach(tab, message, documentUrl = tab.url) {
  const key = sessionKey(tab.id);
  if ((await chrome.storage.session.get(key))[key]) return;
  if (typeof message.selector !== 'string' || !message.selector || message.selector.length > 12000) throw new Error(t('invalidArea'));
  const pageUrl = pageAddress(documentUrl);
  if (!supported(pageUrl)) throw new Error(t('restrictedPage'));
  const saved = tab.incognito ? undefined : (await chrome.storage.local.get(selectionKey(pageUrl)).catch(() => ({})))[selectionKey(pageUrl)];
  const state = {originWindowId: tab.windowId, index: tab.index, url: pageUrl, selectionUrl: pageUrl, selector: message.selector, incognito: tab.incognito, pinned: tab.pinned};
  const tabs = await chrome.tabs.query({windowId: tab.windowId});
  if (tabs.length === 1) state.placeholderId = (await chrome.tabs.create({windowId: tab.windowId, url: 'about:blank', active: false})).id;
  const bounds = saved?.bounds;
  const options = {tabId: tab.id, type: 'popup', incognito: !!tab.incognito, focused: true,
    width: Math.max(320, Math.min(2400, Math.round(message.width || 800))),
    height: Math.max(240, Math.min(1600, Math.round((message.height || 500) + 40)))};
  if (bounds && ['left', 'top', 'width', 'height'].every(field => Number.isSafeInteger(bounds[field])) &&
      bounds.width > 0 && bounds.height > 0) {
    for (const field of ['left', 'top', 'width', 'height']) options[field] = bounds[field];
  }
  try {
    const popup = await chrome.windows.create(options);
    state.popupWindowId = popup.id;
    await chrome.storage.session.set({[key]: state});
  } catch (error) {
    if (state.popupWindowId !== undefined) await moveToNormal(tab.id, state).catch(console.error);
    await removePlaceholder(state);
    throw error;
  }
  // Remembering a selection must not undo a successful move if storage is full.
  if (!tab.incognito) {
    const pageKey = selectionKey(pageUrl);
    await inPreferenceOrder(pageKey, async () => {
      const latest = (await chrome.storage.local.get(pageKey))[pageKey];
      await chrome.storage.local.set({[pageKey]: {...latest, selector: message.selector}});
    }).catch(console.error);
  }
}

async function toggleVideoPin(tabId, selector) {
  const request = crypto.randomUUID();
  const prepared = await chrome.scripting.executeScript({
    target: {tabId, allFrames: true}, args: [request, selector, true], func: routeVideoPinFrame
  });
  const top = prepared.find(frame => frame.frameId === 0 && frame.result);
  if (!top) return {found: false};
  const children = prepared.filter(frame => frame.frameId !== 0 && frame.result);
  const documentIds = [top.documentId];
  if (children.length) {
    const links = await chrome.scripting.executeScript({
      target: {tabId, allFrames: true}, args: [request, selector, false], func: routeVideoPinFrame
    });
    const parentByDocument = new Map(links.map(frame => [frame.documentId, frame.result]));
    const queue = [top.result.id];
    const childrenByParent = new Map();
    for (const child of children) {
      const parentId = parentByDocument.get(child.documentId);
      if (!parentId) continue;
      if (!childrenByParent.has(parentId)) childrenByParent.set(parentId, []);
      childrenByParent.get(parentId).push(child);
    }
    const seen = new Set(documentIds);
    while (queue.length) {
      for (const child of childrenByParent.get(queue.pop()) || []) {
        if (seen.has(child.documentId)) continue;
        seen.add(child.documentId);
        documentIds.push(child.documentId);
        queue.push(child.result.id);
      }
    }
  }
  const frames = await chrome.scripting.executeScript({
    target: {tabId, documentIds}, args: [selector], func: videoPinFrame
  });
  const candidate = frames.filter(frame => frame.result).sort((a, b) =>
    Number(b.result.active) - Number(a.result.active) ||
    Number(b.result.ready) - Number(a.result.ready) ||
    Number(b.result.playing) - Number(a.result.playing) || b.result.area - a.result.area
  )[0];
  if (!candidate) return {found: false};
  const [result] = await chrome.scripting.executeScript({
    target: {tabId, documentIds: [candidate.documentId]}, args: [selector, true], func: videoPinFrame
  });
  if (result?.result?.error) throw new Error(t(result.result.error));
  if (!result?.result) throw new Error(t('pipBlocked'));
  return {found: true, active: result.result.active};
}

async function handle(message, sender) {
  // Content scripts may act only on their own tab; popup commands require an extension page.
  const extensionPage = !sender.tab && sender.url?.startsWith(chrome.runtime.getURL(''));
  const tabId = sender.tab?.id ?? (extensionPage ? message.tabId : undefined);
  if (!Number.isInteger(tabId)) throw new Error(t('noActiveTab'));
  if (sender.tab && sender.frameId !== 0 && message.type !== 'pip-state') throw new Error(t('commandFailed'));
  if (message.type === 'window-state' || message.type === 'pip-state') return handleTab(tabId, message, sender);
  return inTabOrder(tabId, () => handleTab(tabId, message, sender));
}

async function handleTab(tabId, message, sender) {
  const tab = await chrome.tabs.get(tabId);
  const key = sessionKey(tabId);
  const detached = (await chrome.storage.session.get(key))[key];
  const state = detached?.popupWindowId === tab.windowId ? detached : null;
  switch (message.type) {
    case 'auto-pip': {
      if (sender.tab) throw new Error(t('commandFailed'));
      if (tab.incognito || !tab.url?.startsWith('https:')) return {available: false, enabled: false};
      const url = new URL(tab.url);
      const preference = `auto-pip:${url.origin}`;
      return inPreferenceOrder(preference, async () => {
        if (typeof message.enabled !== 'boolean') {
          return {available: true, enabled: (await chrome.storage.local.get(preference))[preference] === true};
        }
        if (message.enabled) await chrome.storage.local.set({[preference]: true});
        else await chrome.storage.local.remove(preference);
        await tell(tabId, 'auto-pip-refresh').catch(() => {});
        return {available: true, enabled: message.enabled};
      });
    }
    case 'clean-media': {
      if (!state || sender.frameId !== 0 || typeof message.selector !== 'string' || message.selector.length > 12000 || !Array.isArray(message.frameRoots) || !message.frameRoots.every(root => typeof root === 'string' && /^\d+$/.test(root))) throw new Error(t('detachFirst'));
      const probes = message.enabled === false ? [] : await chrome.scripting.executeScript({target:{tabId, allFrames:true}, func:cleanMediaFrame, args:[message.selector, message.frameRoots, 'probe']});
      const paths = probes.map(frame => frame.result).filter(path => typeof path === 'string');
      await chrome.scripting.executeScript({target:{tabId, allFrames:true}, func:cleanMediaFrame, args:[message.selector, message.frameRoots, message.enabled !== false, paths]});
      return;
    }
    case 'video-pin': {
      if (!state || sender.frameId !== 0 || typeof message.selector !== 'string' || message.selector.length > 12000) throw new Error(t('detachFirst'));
      return toggleVideoPin(tabId, message.selector);
    }
    case 'pip-state':
      if (sender.tab) await chrome.tabs.sendMessage(tabId, {type: 'pip-state', active: false}, {frameId: 0}).catch(() => {});
      return;
    case 'window-state': {
      const selectionUrl = state?.selectionUrl || state?.url;
      const selector = samePageRoute(selectionUrl, sender.url || tab.url) ? state?.selector : undefined;
      return {detached: !!state, selector, incognito: !!tab.incognito};
    }
    case 'select':
      if (state) return restore(tabId);
      return tell(tabId, 'select');
    case 'restore': return restore(tabId);
    case 'forget':
      if (!tab.incognito && supported(tab.url)) {
        const pageKey = selectionKey(pageAddress(tab.url));
        await inPreferenceOrder(pageKey, () => chrome.storage.local.remove(pageKey));
      }
      return tell(tabId, 'forget');
    case 'detach':
      if (!sender.tab) throw new Error(t('selectFirst'));
      return detach(tab, message, sender.url || tab.url);
    case 'bounds': {
      if (!state) throw new Error(t('detachFirst'));
      if (tab.incognito) throw new Error(t('privateBounds'));
      const pageKey = selectionKey(pageAddress(tab.url));
      const win = await chrome.windows.get(tab.windowId);
      return inPreferenceOrder(pageKey, async () => {
        const saved = (await chrome.storage.local.get(pageKey))[pageKey] || {};
        const bounds = saved.bounds ? undefined : {left: win.left, top: win.top, width: win.width, height: win.height};
        if (bounds) saved.bounds = bounds;
        else delete saved.bounds;
        await chrome.storage.local.set({[pageKey]: saved});
        return {saved: !!bounds};
      });
    }
    case 'bookmark': {
      if (!state || typeof message.url !== 'string') throw new Error(t('detachFirst'));
      const link = new URL(message.url);
      const source = new URL(tab.url);
      if (link.origin !== source.origin || link.pathname !== source.pathname || !supported(link.href)) throw new Error(t('invalidLink'));
      await inPreferenceOrder('bookmarks', async () => {
        const folders = await chrome.bookmarks.search({title: 'Separate windows'});
        let folder = folders.find(item => !item.url);
        if (!folder) folder = await chrome.bookmarks.create({title: 'Separate windows'});
        await chrome.bookmarks.create({parentId: folder.id, title: tab.title || 'Separate Window', url: link.href});
      });
      return;
    }
    case 'capture': {
      if (!state) throw new Error(t('noSeparateWindow'));
      async function stillActive() {
        const [active] = await chrome.tabs.query({active: true, windowId: tab.windowId});
        if (active?.id !== tabId) throw new Error(t('activePageRequired'));
      }
      await stillActive();
      const image = await chrome.tabs.captureVisibleTab(tab.windowId, {format: 'png'});
      await stillActive();
      return {image};
    }
    default: throw new Error(t('unknownCommand'));
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || typeof message?.type !== 'string') return false;
  const task = message.type === 'translations' ? SWI18n.reload().then(() => ({language:SWI18n.language, preference:SWI18n.preference, messages:SWI18n.messages})) : SWI18n.ready.then(() => handle(message, sender));
  task.then(result => respond({ok: true, ...result}), error => respond({ok: false, error: error.message}));
  return true;
});
chrome.runtime.onInstalled.addListener(async () => {
  await SWI18n.ready;
  chrome.contextMenus.removeAll(() => chrome.contextMenus.create({id: 'select', title: t('contextMenu'), contexts: ['all'], documentUrlPatterns: ['http://*/*', 'https://*/*', 'file:///*']}));
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'select' && tab) toggleSelection(tab.id).catch(console.error);
});
SWI18n.onChange(() => chrome.contextMenus.update('select', {title:t('contextMenu')}).catch(() => {}));
chrome.commands.onCommand.addListener(async (command, triggeredTab) => {
  if (command !== 'select') return;
  await SWI18n.ready;
  const tab = triggeredTab || (await chrome.tabs.query({active: true, lastFocusedWindow: true}))[0];
  if (tab) toggleSelection(tab.id).catch(console.error);
});
function toggleSelection(tabId) {
  return handle({type: 'select', tabId}, {url: chrome.runtime.getURL('popup.html')});
}
chrome.tabs.onUpdated.addListener((tabId, change) => {
  if (!supported(change.url)) return;
  const key = sessionKey(tabId);
  inTabOrder(tabId, async () => {
    const state = (await chrome.storage.session.get(key))[key];
    if (state) await chrome.storage.session.set({[key]: {...state, url: pageAddress(change.url)}});
  }).catch(console.error);
});

chrome.tabs.onAttached.addListener((tabId, info) => {
  inTabOrder(tabId, async () => {
    const key = sessionKey(tabId);
    const state = (await chrome.storage.session.get(key))[key];
    if (!state || state.popupWindowId === info.newWindowId) return;
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (tab && tab.windowId !== state.popupWindowId) await finishRestore(tabId, state);
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
      const window = await chrome.windows.create({url: state.url, type: 'normal', incognito: !!state.incognito, focused: true});
      if (state.pinned) {
        const [tab] = await chrome.tabs.query({windowId: window.id});
        if (tab) await chrome.tabs.update(tab.id, {pinned: true}).catch(() => {});
      }
    }
  }
  await removePlaceholder(state);
  await chrome.storage.session.remove(key);
}
chrome.tabs.onRemoved.addListener((tabId, info) => {
  inTabOrder(tabId, () => recoverClosedPopup(tabId, info)).catch(console.error);
});
