(() => {
  const t = (key, substitutions) => chrome.i18n.getMessage(key, substitutions);
  if (globalThis.__separateWindowLocal) return;
  globalThis.__separateWindowLocal = true;
  const token = `sw-${crypto.randomUUID().replaceAll('-', '')}`;
  const targetAttr = `data-${token}-target`;
  const ancestorAttr = `data-${token}-ancestor`;
  let selected, selector, sourceUrl, initialSize, cropStyle, ui, shadow, picker;
  let ancestors = [], scale = 1, rotation = 0, brightness = 1, fit = true;
  let marker, markerTarget, savedSelector, noticeTimer, detached = false;

  async function send(type, extra = {}) {
    const result = await chrome.runtime.sendMessage({type, ...extra});
    if (!result?.ok) throw new Error(result?.error || t('unavailable'));
    return result;
  }

  function makeUI() {
    const host = document.createElement('div');
    host.setAttribute(`data-${token}-ui`, '');
    host.style.cssText = 'all:initial!important;position:fixed!important;inset:0!important;z-index:2147483647!important;pointer-events:none!important;visibility:visible!important;display:block!important;';
    const root = host.attachShadow({mode: 'closed'});
    const style = document.createElement('style');
    style.textContent = `
      :host{color-scheme:dark}*{box-sizing:border-box}button,input{font:13px system-ui,sans-serif}
      button{border:1px solid #526077;background:#263349;color:#fff;border-radius:5px;padding:6px 9px;cursor:pointer;white-space:nowrap}
      button:hover{background:#3c5273}button:focus-visible,input:focus-visible{outline:2px solid #9fc5ff;outline-offset:2px}
      .bar{pointer-events:auto;position:fixed;top:0;right:0;width:max-content;max-width:100%;padding:6px;display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:5px;opacity:0;transition:opacity 120ms ease-out}
      .bar:hover,.bar:focus-within{opacity:.75}.bar:focus-within{transition:none}
      .bar button,.bar input{pointer-events:none}.bar:hover button,.bar:hover input,.bar:focus-within button,.bar:focus-within input{pointer-events:auto}
      .bar button{background:#152031}.bar button:hover{background:#344963}.bar span{font:12px system-ui;color:#fff;white-space:nowrap;text-shadow:0 1px 3px #000}
      @media(prefers-reduced-motion:reduce){.bar{transition:none}}
      .outline{position:fixed;border:3px solid #5089ff;background:#5089ff18;pointer-events:none}
      .shield{position:fixed;inset:0;pointer-events:auto;cursor:crosshair;touch-action:none;outline:none}
      .hint,.notice{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:90vw;padding:12px 18px;border-radius:8px;background:#101a2b;color:#fff;font:14px/1.5 system-ui;text-align:center;box-shadow:0 3px 15px #0005;pointer-events:auto}
      .hint button{margin-left:12px}.marker{position:fixed;pointer-events:auto;background:#2357d9;box-shadow:0 2px 8px #0005}
      input[type=range]{width:75px}dialog{pointer-events:auto;max-width:90vw;width:560px;border:1px solid #526077;border-radius:12px;background:#101a2b;color:#fff;padding:20px;font:14px system-ui}dialog::backdrop{background:#0008}dialog input{width:100%;padding:10px;margin:12px 0;color:#fff;background:#263349;border:1px solid #526077}
    `;
    root.append(style);
    document.documentElement.append(host);
    return {host, root};
  }

  function notify(text) {
    if (!ui) ({host: ui, root: shadow} = makeUI());
    shadow.querySelector('.notice')?.remove();
    const node = document.createElement('div');
    node.className = 'notice'; node.setAttribute('role', 'status'); node.textContent = text;
    shadow.append(node); clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => {node.remove(); if (!selected && !picker) {ui?.remove(); ui = null;}}, 5000);
  }

  function cssSelector(element) {
    const parts = [];
    for (let node = element; node && node !== document.documentElement; node = node.parentElement) {
      if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) {
        parts.unshift(`#${CSS.escape(node.id)}`); break;
      }
      let part = node.localName;
      if (!part) throw new Error(t('cannotSelect'));
      const peers = [...(node.parentElement?.children || [])].filter(item => item.localName === node.localName);
      if (peers.length > 1) part += `:nth-of-type(${peers.indexOf(node) + 1})`;
      parts.unshift(part);
    }
    return parts.join(' > ');
  }

  function stopPicker() {
    if (!picker) return;
    const {controller, host, previousFocus} = picker;
    controller.abort(); host.remove(); picker = null;
    if (previousFocus?.isConnected) previousFocus.focus({preventScroll: true});
  }

  function startPicker() {
    if (selected) return;
    stopPicker(); removeMarker();
    const previousFocus = document.activeElement;
    const {host, root} = makeUI();
    // A parent document cannot receive pointer events from a cross-origin iframe.
    // Catch the entire gesture above the page, then hit-test underneath this host.
    const shield = document.createElement('div'); shield.className = 'shield'; shield.tabIndex = -1;
    const outline = document.createElement('div'); outline.className = 'outline';
    const hint = document.createElement('div'); hint.className = 'hint';
    hint.textContent = t('pickerHint');
    const cancel = document.createElement('button'); cancel.textContent = t('cancel');
    cancel.onclick = stopPicker; hint.append(cancel); root.append(shield, outline, hint);
    const controller = new AbortController();
    picker = {host, controller, previousFocus, chain: [], index: 0};
    shield.focus({preventScroll: true});
    const options = {capture: true, signal: controller.signal};
    function draw() {
      if (!picker?.chain.length) return;
      const rect = picker.chain[picker.index].getBoundingClientRect();
      outline.style.cssText = `left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px`;
    }
    function hover(event) {
      if (event.composedPath().includes(hint)) return;
      // elementFromPoint selects an iframe as a whole, preserving its live document.
      let element = document.elementsFromPoint(event.clientX, event.clientY).find(element => element !== host);
      if (!element || element === document.documentElement) return;
      if (element === picker.chain[0]) return;
      picker.chain = [];
      while (element && element !== document.documentElement) {picker.chain.push(element); element = element.parentElement;}
      picker.index = 0; draw();
    }
    document.addEventListener('pointermove', hover, options);
    for (const type of ['pointerdown', 'pointerup', 'mousedown', 'mouseup', 'touchstart', 'touchend', 'dblclick', 'contextmenu']) {
      document.addEventListener(type, event => {
        if (event.composedPath().includes(hint)) return;
        event.preventDefault(); event.stopImmediatePropagation();
      }, {...options, passive: false});
    }
    document.addEventListener('wheel', event => {
      if (!picker.chain.length) hover(event);
      if (!picker.chain.length || event.composedPath().includes(hint)) return;
      event.preventDefault(); event.stopImmediatePropagation();
      picker.index = Math.max(0, Math.min(picker.chain.length - 1, picker.index + (event.deltaY > 0 ? 1 : -1)));
      draw();
    }, {...options, passive: false});
    document.addEventListener('click', event => {
      if (event.composedPath().includes(hint)) return;
      if (!picker.chain.length) hover(event);
      event.preventDefault(); event.stopImmediatePropagation();
      const element = picker.chain[picker.index];
      stopPicker();
      if (element) openElement(element).catch(error => notify(error.message));
    }, options);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') {event.preventDefault(); event.stopImmediatePropagation(); stopPicker();}
    }, options);
    // Wait until Chromium has painted the shield and updated iframe hit testing.
    return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }

  function renderCrop() {
    if (!selected) return;
    const w = initialSize.width, h = initialSize.height;
    const availableW = window.innerWidth, availableH = window.innerHeight;
    const rotated = rotation % 180 !== 0;
    const factor = fit ? Math.min(availableW / (rotated ? h : w), availableH / (rotated ? w : h)) * scale : scale;
    const target = `[${targetAttr}]`, ancestor = `[${ancestorAttr}]`, host = `[data-${token}-ui]`;
    cropStyle.textContent = `
      html,body{overflow:hidden!important;min-width:0!important;min-height:0!important}
      ${ancestor}{display:contents!important;position:static!important;margin:0!important;padding:0!important;background:none!important;border:0!important;border-radius:0!important;box-shadow:none!important;outline:0!important;transform:none!important;translate:none!important;rotate:none!important;scale:none!important;zoom:1!important;filter:none!important;backdrop-filter:none!important;perspective:none!important;contain:none!important;container-type:normal!important;content-visibility:visible!important;clip:auto!important;clip-path:none!important;overflow:visible!important;opacity:1!important;isolation:auto!important;mix-blend-mode:normal!important;will-change:auto!important}
      ${ancestor}::before,${ancestor}::after{content:none!important;display:none!important}
      html${ancestor}{display:block!important;background:#000!important}
      ${ancestor} > :not(${ancestor}):not(${target}):not(${host}):not(style):not(script):not(link){display:none!important}
      ${target}{display:${initialSize.display}!important;position:fixed!important;inset:auto!important;left:50%!important;top:50%!important;width:${w}px!important;height:${h}px!important;min-width:0!important;min-height:0!important;max-width:none!important;max-height:none!important;margin:0!important;z-index:2147483640!important;translate:none!important;rotate:none!important;scale:none!important;zoom:1!important;transform:translate(-50%,-50%) rotate(${rotation}deg) scale(${factor})!important;transform-origin:center!important;filter:brightness(${brightness})!important;box-sizing:border-box!important;visibility:visible!important;}
      ${host}{display:block!important}
    `;
  }

  function unCrop(showMarker = true) {
    stopPicker();
    cropStyle?.remove(); cropStyle = null;
    selected?.removeAttribute(targetAttr);
    for (const ancestor of ancestors) ancestor.removeAttribute(ancestorAttr);
    ancestors = []; selected = null; detached = false;
    ui?.remove(); ui = null; shadow = null;
    if (showMarker) installMarker(savedSelector);
  }

  function windowLink() {
    const url = new URL(sourceUrl);
    url.hash = `__sw_local=${encodeURIComponent(JSON.stringify({selector, hash: url.hash}))}`;
    return url.href;
  }

  async function screenshot() {
    ui.style.setProperty('visibility', 'hidden', 'important');
    try {
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const {image} = await send('capture');
      const img = new Image(); img.src = image; await img.decode();
      const rect = selected.getBoundingClientRect();
      const x = Math.max(0, rect.left), y = Math.max(0, rect.top);
      const w = Math.min(innerWidth, rect.right) - x, h = Math.min(innerHeight, rect.bottom) - y;
      if (w <= 0 || h <= 0) throw new Error(t('outsideViewport'));
      const ratioX = img.width / innerWidth, ratioY = img.height / innerHeight;
      const canvas = document.createElement('canvas'); canvas.width = Math.round(w * ratioX); canvas.height = Math.round(h * ratioY);
      canvas.getContext('2d').drawImage(img, x * ratioX, y * ratioY, w * ratioX, h * ratioY, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error(t('pngFailed'));
      const url = URL.createObjectURL(blob), a = document.createElement('a');
      a.href = url; a.download = `separate-window-${Date.now()}.png`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } finally {ui?.style.setProperty('visibility', 'visible', 'important');}
  }

  function toolbar() {
    ({host: ui, root: shadow} = makeUI());
    const bar = document.createElement('div'); bar.className = 'bar'; bar.setAttribute('aria-label', t('controls'));
    bar.addEventListener('pointerleave', () => shadow?.activeElement?.blur());
    bar.addEventListener('keydown', event => {
      if (event.key === 'Escape') {shadow.activeElement?.blur(); event.stopPropagation();}
    });
    function button(text, title, action) {
      const button = document.createElement('button'); button.textContent = text; button.title = title;
      button.setAttribute('aria-label', title);
      button.onclick = async () => {try {await action(button); renderCrop();} catch (error) {notify(error.message);}};
      bar.append(button);
    }
    button(t('returnShort'), t('returnTitle'), () => send('restore'));
    button(t('size'), t('sizeTitle'), async button => {
      const result = await send('bounds'); button.textContent = result.saved ? t('sizeSaved') : t('size');
      notify(result.saved ? t('sizeSavedNotice') : t('sizeForgottenNotice'));
    });
    button('−', t('zoomOut'), () => {scale = Math.max(.1, scale - .1); renderCrop();});
    button('+', t('zoomIn'), () => {scale = Math.min(5, scale + .1); renderCrop();});
    button(t('fit'), t('fitTitle'), button => {fit = !fit; scale = 1; button.textContent = fit ? t('fit') : '1:1'; renderCrop();});
    button('↻', t('rotateTitle'), () => {rotation = (rotation + 90) % 360; renderCrop();});
    const label = document.createElement('span'); label.textContent = t('brightness');
    const range = document.createElement('input'); range.type = 'range'; range.min = '.2'; range.max = '2.5'; range.step = '.1'; range.value = '1'; range.setAttribute('aria-label', t('brightness'));
    range.oninput = () => {brightness = Number(range.value); renderCrop();}; bar.append(label, range);
    button(t('snapshot'), t('snapshotTitle'), screenshot);
    button('★', t('bookmarkTitle'), async () => {await send('bookmark', {url: windowLink()}); notify(t('bookmarkSaved'));});
    button(t('link'), t('linkTitle'), async () => {
      const dialog = document.createElement('dialog');
      const text = document.createElement('div'); text.textContent = t('linkHelp');
      const input = document.createElement('input'); input.readOnly = true; input.value = windowLink(); input.setAttribute('aria-label', t('blockLink'));
      const close = document.createElement('button'); close.textContent = t('close'); close.onclick = () => {dialog.close(); dialog.remove();};
      dialog.append(text, input, close); shadow.append(dialog); dialog.showModal(); input.focus(); input.select();
    });
    button('⛶', t('fullscreen'), () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen());
    shadow.append(bar);
  }

  async function openElement(element) {
    if (selected) return;
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) throw new Error(t('hiddenBlock'));
    selector = cssSelector(element); savedSelector = selector; sourceUrl = location.href;
    initialSize = {width: rect.width, height: rect.height, display: getComputedStyle(element).display};
    selected = element; scale = 1; rotation = 0; brightness = 1; fit = true;
    removeMarker(); selected.setAttribute(targetAttr, '');
    for (let ancestor = selected.parentElement; ancestor; ancestor = ancestor.parentElement) {ancestor.setAttribute(ancestorAttr, ''); ancestors.push(ancestor);}
    cropStyle = document.createElement('style'); document.documentElement.append(cropStyle);
    toolbar(); renderCrop();
    try {await send('detach', {selector, width: rect.width, height: rect.height}); detached = true;}
    catch (error) {unCrop(); throw error;}
  }

  function positionMarker() {
    if (!marker || !markerTarget?.isConnected) return;
    const rect = markerTarget.getBoundingClientRect();
    marker.style.left = `${Math.max(0, rect.left)}px`; marker.style.top = `${Math.max(0, rect.top)}px`;
    marker.hidden = rect.bottom < 0 || rect.top > innerHeight || !rect.width || !rect.height;
  }
  function removeMarker() {
    marker?.getRootNode().host?.remove(); marker = null; markerTarget = null;
  }
  function installMarker(value) {
    removeMarker();
    if (!value || selected || picker || detached) return false;
    let element;
    try {element = document.querySelector(value);} catch {return false;}
    if (!element) return false;
    const {root} = makeUI();
    marker = document.createElement('button'); marker.className = 'marker'; marker.textContent = t('marker');
    markerTarget = element; marker.onclick = () => openElement(element).catch(error => notify(error.message));
    root.append(marker); positionMarker(); return true;
  }

  window.addEventListener('resize', () => {renderCrop(); positionMarker();});
  window.addEventListener('scroll', positionMarker, {passive: true, capture: true});
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id) return;
    switch (message.type) {
      case 'select':
        Promise.resolve(startPicker()).then(() => respond({ok: true}), error => respond({ok: false, error: error.message}));
        return true;
      case 'uncrop': unCrop(false); break;
      case 'returned': detached = false; installMarker(savedSelector); break;
      case 'forget':
        chrome.storage.local.remove(`selection:${location.href}`).catch(error => notify(error.message));
        savedSelector = null; removeMarker(); break;
      default: return;
    }
    respond({ok: true});
  });

  async function init() {
    const context = await send('window-state');
    detached = context.detached;
    let automatic = false;
    if (location.hash.startsWith('#__sw_local=')) {
      try {
        const data = JSON.parse(decodeURIComponent(location.hash.slice(12)));
        if (typeof data.selector !== 'string' || data.selector.length > 12000 || typeof data.hash !== 'string' || (data.hash && !data.hash.startsWith('#'))) throw new Error(t('invalidBlockLink'));
        savedSelector = data.selector; automatic = true;
        history.replaceState(history.state, '', location.pathname + location.search + data.hash);
      } catch (error) {notify(t('linkError', error.message)); return;}
    } else {
      const key = `selection:${location.href}`;
      savedSelector = (await chrome.storage.local.get(key))[key]?.selector;
    }
    if (detached) {savedSelector ||= context.selector; automatic = true;}
    if (!savedSelector) return;
    function attempt() {
      let element;
      try {element = document.querySelector(savedSelector);} catch {return true;}
      if (!element || !element.getBoundingClientRect().width) return false;
      if (automatic) openElement(element).catch(error => notify(error.message));
      else installMarker(savedSelector);
      return true;
    }
    if (attempt()) return;
    const observer = new MutationObserver(() => {if (attempt()) observer.disconnect();});
    observer.observe(document.documentElement, {childList: true, subtree: true});
    setTimeout(() => {observer.disconnect(); if (automatic && !selected) notify(t('blockNotFound'));}, 15000);
  }
  window.addEventListener('hashchange', () => {
    if (!selected && location.hash.startsWith('#__sw_local=')) init().catch(error => notify(error.message));
  });
  init().catch(error => notify(error.message));
})();
