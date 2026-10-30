// Serialized by scripting.executeScript into the extension's isolated world.
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
  if (enabled === 'probe') {
    const r = scope.getBoundingClientRect(), area = path.length ? innerWidth * innerHeight : r.width * r.height;
    const videos = [...scope.querySelectorAll('video'), ...(scope.matches('video') ? [scope] : [])];
    return videos.some(video => {const v = video.getBoundingClientRect(); return v.width * v.height >= area * .5 && v.width > 0 && getComputedStyle(video).visibility !== 'hidden';}) ? key : null;
  }
  const token = 'data-sw-media-' + crypto.randomUUID().replaceAll('-', '');
  const branch = token + '-branch', targetAttr = token + '-target';
  let target, controls, style, ancestors = [];
  function reset() {
    style?.remove();
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
    const nodes = [...scope.querySelectorAll('video,iframe'), ...(scope.matches('video,iframe') ? [scope] : [])];
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
    target.removeAttribute('controls'); target.setAttribute(targetAttr, '');
    if (target === scope && !path.length) {
      style = document.createElement('style');
      style.textContent = `[${targetAttr}]{border:0!important;outline:0!important;box-shadow:none!important;object-fit:contain!important;background:#000!important}`;
      document.documentElement.append(style); return;
    }
    for (let node = target.parentElement; node; node = node.parentElement) {
      node.setAttribute(branch, ''); ancestors.push(node);
      if (node === scope) break;
    }
    style = document.createElement('style');
    const b = `[${branch}]`, t = `[${targetAttr}]`;
    style.textContent = `
      ${b}:not(${path.length ? 'html' : selector}){display:contents!important;position:static!important;transform:none!important;filter:none!important;contain:none!important;overflow:visible!important;background:none!important;border:0!important;padding:0!important;margin:0!important;box-shadow:none!important}
      ${b}::before,${b}::after{display:none!important;content:none!important}
      ${b}>:not(${b}):not(${t}):not(style):not(script):not(link){display:none!important}
      ${path.length ? 'html,body{background:#000!important;overflow:hidden!important;margin:0!important;padding:0!important}' : ''}
      ${t}{position:${path.length ? 'fixed' : 'absolute'}!important;inset:0!important;width:100%!important;height:100%!important;max-width:none!important;max-height:none!important;min-width:0!important;min-height:0!important;transform:none!important;margin:0!important;padding:0!important;border:0!important;object-fit:contain!important;background:#000!important;visibility:visible!important}
    `;
    document.documentElement.append(style);
  }
  const observer = new MutationObserver(update);
  observer.observe(scope, {subtree:true, childList:true, attributes:true, attributeFilter:['controls']});
  document.addEventListener('loadedmetadata', update, true);
  update();
  globalThis.__swCleanMedia = () => {
    observer.disconnect(); document.removeEventListener('loadedmetadata', update, true); reset();
  };
}
