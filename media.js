// Serialized by scripting.executeScript into the extension's isolated world.
function routeVideoPinFrame(request, selector, prepare) {
  const channel = 'separate-window:video-frame';
  if (prepare) {
    const scope = window === window.top ? document.querySelector(selector) : document.documentElement;
    if (!scope) return null;
    const id = crypto.randomUUID();
    const controller = new AbortController();
    globalThis.__swVideoRoute?.controller.abort();
    globalThis.__swVideoRoute = {request, id, controller};
    setTimeout(() => controller.abort(), 2500);

    // Indexes from window.frames omit iframes in shadow trees. Match the
    // browser-provided source window to the actual iframe in this DOM branch.
    let children;
    function childWindows() {
      const windows = new Set();
      const bounds = scope.getBoundingClientRect();
      const minimumArea = Math.min(innerWidth, bounds.width) *
        (window === window.top ? Math.min(innerHeight, bounds.height) : innerHeight) / 2;
      const pending = [scope];
      while (pending.length) {
        const node = pending.pop();
        if (node.matches('iframe,frame')) {
          const rect = node.getBoundingClientRect();
          if (node.contentWindow && rect.width > 0 && rect.height > 0 &&
              rect.width * rect.height >= minimumArea && getComputedStyle(node).visibility === 'visible') {
            windows.add(node.contentWindow);
          }
          continue;
        }
        const shadow = node instanceof HTMLElement && (node.shadowRoot || chrome.dom?.openOrClosedShadowRoot(node));
        for (const child of node.children) pending.push(child);
        if (shadow) for (const child of shadow.children) pending.push(child);
      }
      return windows;
    }

    window.addEventListener('message', event => {
      const data = event.data;
      if (!event.isTrusted || !event.source || data?.channel !== channel || data.request !== request ||
          data.kind !== 'link' || typeof data.id !== 'string') return;
      children ??= childWindows();
      event.source.postMessage({channel, request, kind: 'parent', id: data.id,
        parentId: children.has(event.source) ? id : null}, event.origin === 'null' ? '*' : event.origin);
    }, {signal: controller.signal});
    return {id};
  }

  const route = globalThis.__swVideoRoute;
  if (window === window.top || route?.request !== request || route.controller.signal.aborted) return null;
  const {id} = route;
  return new Promise(resolve => {
    const listener = new AbortController();
    const timer = setTimeout(() => finish(null), 500);
    function finish(parentId) {
      clearTimeout(timer);
      listener.abort();
      resolve(parentId);
    }
    window.addEventListener('message', event => {
      const data = event.data;
      if (event.isTrusted && event.source === window.parent && data?.channel === channel &&
          data.request === request && data.kind === 'parent' && data.id === id) {
        finish(typeof data.parentId === 'string' ? data.parentId : null);
      }
    }, {signal: listener.signal});
    window.parent.postMessage({channel, request, kind: 'link', id}, '*');
  });
}

async function videoPinFrame(selector, toggle = false) {
  const scope = window === window.top ? document.querySelector(selector) : document.documentElement;
  const candidates = [];
  if (scope) {
    const bounds = scope.getBoundingClientRect();
    // A small embedded clip should not replace a dashboard or a larger block.
    const minimumArea = Math.min(innerWidth, bounds.width) *
      (window === window.top ? Math.min(innerHeight, bounds.height) : innerHeight) / 2;
    const pending = [scope];
    while (pending.length) {
      const node = pending.pop();
      if (node instanceof HTMLVideoElement) {
        const rect = node.getBoundingClientRect();
        const active = node.getRootNode().pictureInPictureElement === node;
        const area = rect.width * rect.height;
        const ready = !!(node.videoWidth && node.readyState);
        if (active || (area > 0 && area >= minimumArea &&
            getComputedStyle(node).visibility === 'visible')) {
          candidates.push({video: node, active, ready, playing: ready && !node.paused && !node.ended, area});
        }
        continue;
      }
      for (const child of node.children) pending.push(child);
      if (node instanceof HTMLElement) {
        const shadow = node.shadowRoot || chrome.dom?.openOrClosedShadowRoot(node);
        if (shadow) for (const child of shadow.children) pending.push(child);
      }
    }
  }
  const candidate = candidates.sort((a, b) =>
    Number(b.active) - Number(a.active) || Number(b.ready) - Number(a.ready) ||
    Number(b.playing) - Number(a.playing) || b.area - a.area
  )[0];
  if (!candidate) return toggle ? {error: 'pipNoVideo'} : null;
  const {video, active, ready, playing, area} = candidate;
  if (!toggle) return {active, ready, playing, area};
  try {
    if (active) {
      await document.exitPictureInPicture();
      return {active: false};
    }
    if (!ready) return {error: 'pipNoVideo'};
    if (!document.pictureInPictureEnabled || video.disablePictureInPicture) return {error: 'pipBlocked'};
    await video.requestPictureInPicture();
    globalThis.__swPinnedVideo = video;
    video.addEventListener('leavepictureinpicture', () => {
      if (globalThis.__swPinnedVideo === video) delete globalThis.__swPinnedVideo;
      chrome.runtime.sendMessage({type: 'pip-state', active: false}).catch(() => {});
    }, {once: true});
    return {active: true};
  } catch {
    return {error: 'pipBlocked'};
  }
}

async function resetDetachedMedia() {
  globalThis.__swCleanMedia?.();
  delete globalThis.__swCleanMedia;
  const video = globalThis.__swPinnedVideo;
  delete globalThis.__swPinnedVideo;
  if (video && video.getRootNode().pictureInPictureElement === video) {
    await document.exitPictureInPicture().catch(() => {});
  }
}

function cleanMediaFrame(selector, roots, enabled, mediaPaths = []) {
  if (enabled !== 'probe') {globalThis.__swCleanMedia?.(); delete globalThis.__swCleanMedia;}
  if (!enabled) return;
  const path = [];
  for (let win = window; win !== win.top; win = win.parent) {
    let index = 0;
    while (index < win.parent.length && win.parent[index] !== win) index++;
    path.unshift(index);
  }
  const key = path.join('.');
  if (path.length && !roots.some(root => key === root || key.startsWith(root + '.'))) return;
  const scope = path.length ? document.documentElement : document.querySelector(selector);
  if (!scope) return;
  function mediaNodes(includeFrames, onShadow) {
    const result = [], pending = [scope];
    while (pending.length) {
      const node = pending.pop();
      if (node.matches(includeFrames ? 'video,iframe' : 'video')) {
        result.push(node);
        continue;
      }
      const shadow = node instanceof HTMLElement && (node.shadowRoot || chrome.dom?.openOrClosedShadowRoot(node));
      if (shadow) {
        onShadow?.(shadow);
        for (let i = shadow.children.length - 1; i >= 0; i--) pending.push(shadow.children[i]);
      }
      for (let i = node.children.length - 1; i >= 0; i--) pending.push(node.children[i]);
    }
    return result;
  }
  if (enabled === 'probe') {
    const r = scope.getBoundingClientRect(), area = path.length ? innerWidth * innerHeight : r.width * r.height;
    const videos = mediaNodes(false);
    return videos.some(video => {const v = video.getBoundingClientRect(); return v.width * v.height >= area * .5 && v.width > 0 && getComputedStyle(video).visibility !== 'hidden';}) ? key : null;
  }
  const token = 'data-sw-media-' + crypto.randomUUID().replaceAll('-', '');
  const branch = token + '-branch', targetAttr = token + '-target';
  let target, controls;
  let styles = [], ancestors = [];
  const shadowRoots = new Set();
  function addStyle(root, css) {
    const style = document.createElement('style');
    style.textContent = css;
    (root === document ? document.documentElement : root).append(style);
    styles.push(style);
  }
  function reset() {
    for (const style of styles) style.remove();
    styles = [];
    target?.removeAttribute(targetAttr);
    if (target?.localName === 'video' && controls) target.setAttribute('controls', '');
    for (const node of ancestors) node.removeAttribute(branch);
    ancestors = []; target = null;
  }
  function update() {
    if (target?.isConnected) {
      if (target.localName === 'video' && target.hasAttribute('controls')) target.removeAttribute('controls');
      return;
    }
    reset();
    const scopeRect = scope.getBoundingClientRect();
    const area = path.length ? innerWidth * innerHeight : scopeRect.width * scopeRect.height;
    const nodes = mediaNodes(true, observeShadow);
    const candidates = nodes.filter(node => {
      const r = node.getBoundingClientRect();
      if (node.localName === 'iframe') {
        const owner = node.contentWindow;
        let childPath = key;
        if (owner !== window) {
          let index = 0; while (index < window.length && window[index] !== owner) index++;
          childPath = [...path,index].join('.');
        }
        if (!mediaPaths.some(media => media === childPath || media.startsWith(childPath + '.'))) return false;
      }
      return r.width * r.height >= area * .5 && getComputedStyle(node).visibility !== 'hidden' &&
        (node.localName !== 'video' || node.readyState > 0);
    }).sort((a,b) => Number(b.localName === 'video') - Number(a.localName === 'video') ||
      b.getBoundingClientRect().width * b.getBoundingClientRect().height - a.getBoundingClientRect().width * a.getBoundingClientRect().height);
    target = candidates[0];
    if (!target) return;
    controls = target.localName === 'video' && target.hasAttribute('controls');
    if (target.localName === 'video') target.removeAttribute('controls');
    target.setAttribute(targetAttr, '');
    if (target === scope && !path.length) {
      addStyle(document, `[${targetAttr}]{border:0!important;outline:0!important;box-shadow:none!important;object-fit:contain!important;background:#000!important}`);
      return;
    }
    const parent = node => node.parentElement || node.getRootNode().host;
    for (let node = parent(target); node; node = parent(node)) {
      node.setAttribute(branch, ''); ancestors.push(node);
      if (node === scope) break;
    }
    const b = `[${branch}]`, t = `[${targetAttr}]`;
    const hideSiblings = `> :not(${b}):not(${t}):not(style):not(script):not(link){display:none!important}`;
    const rules = `
      ${b}:not(${path.length ? 'html' : selector}){display:contents!important;position:static!important;transform:none!important;filter:none!important;contain:none!important;overflow:visible!important;background:none!important;border:0!important;padding:0!important;margin:0!important;box-shadow:none!important}
      ${b}::before,${b}::after{display:none!important;content:none!important}
      ${b} ${hideSiblings}
      ${t}{position:${path.length ? 'fixed' : 'absolute'}!important;inset:0!important;width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;min-width:0!important;min-height:0!important;transform:none!important;margin:0!important;padding:0!important;border:0!important;object-fit:contain!important;background:#000!important;visibility:visible!important}
    `;
    const roots = new Set([target.getRootNode(), ...ancestors.map(node => node.getRootNode())]);
    for (const root of roots) {
      const rootRules = root !== document ? `:host(${b}) ${hideSiblings}` :
        path.length ? 'html,body{background:#000!important;overflow:hidden!important;margin:0!important;padding:0!important}' : '';
      addStyle(root, `${rules}\n${rootRules}`);
    }
  }
  const observer = new MutationObserver(update);
  const observation = {subtree:true, childList:true, attributes:true, attributeFilter:['controls']};
  function observeShadow(root) {
    if (shadowRoots.has(root)) return;
    shadowRoots.add(root);
    observer.observe(root, observation);
    root.addEventListener('loadedmetadata', update, true);
  }
  observer.observe(scope, observation);
  document.addEventListener('loadedmetadata', update, true);
  update();
  globalThis.__swCleanMedia = () => {
    observer.disconnect();
    document.removeEventListener('loadedmetadata', update, true);
    for (const root of shadowRoots) root.removeEventListener('loadedmetadata', update, true);
    reset();
  };
}
