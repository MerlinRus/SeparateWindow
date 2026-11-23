(() => {
  const t = (key, substitutions) => SWI18n.t(key, substitutions);
  if (globalThis.__separateWindowLocal) return;
  globalThis.__separateWindowLocal = true;
  const initialUrl = location.href;
  const tourPage = location.origin === 'https://separate.maark.ru' &&
    /^\/(?:en\/)?onboarding\/?$/.test(location.pathname);
  const tourStateAttr = 'data-separate-window-tour';
  let tourExample;
  const documentReady = document.readyState === 'loading'
    ? new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, {once: true}))
    : Promise.resolve();
  const roots = new Set();
  SWI18n.onChange(old => {
    for (const root of roots) {
      if (!root.host.isConnected) {roots.delete(root); continue;}
      root.host.lang = SWI18n.language;
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let node; (node = walker.nextNode());) node.textContent = SWI18n.translate(node.textContent, old);
      for (const element of root.querySelectorAll('*')) for (const attr of ['title','aria-label','placeholder']) {
        if (element.hasAttribute(attr)) element.setAttribute(attr, SWI18n.translate(element.getAttribute(attr), old));
      }
    }
    if (blockPreview?.window && !blockPreview.window.closed) {
      blockPreview.window.document.title = t('pinPreviewTitle');
      blockPreview.video.setAttribute('aria-label', t('pinPreviewTitle'));
    }
  });
  const token = `sw-${crypto.randomUUID().replaceAll('-', '')}`;
  const targetAttr = `data-${token}-target`;
  const ancestorAttr = `data-${token}-ancestor`;
  const playerControlsAttr = `data-${token}-player-controls`;
  let selected, selector, sourceUrl, initialSize, cropStyle, ui, shadow, picker, recoveryTimer;
  let selectionObserver, selectionTimer, selectionGeneration = 0;
  let ancestors = [], ancestorLayout = [], cropBackground, cropObserver, scale = 1, rotation = 0, fit = true;
  let marker, markerTarget, markerEvents, savedSelector, noticeTimer, detached = false, pinButton, pipActive = false, cleanVideo = false;
  let blockPreview;
  let blockPreviewRequestSize;
  let playerControls;
  let toolbarEvents;
  const youtubePlayerSelector = '#movie_player.html5-video-player';
  const twitchPlayerSelector = '[data-a-target="video-player"],[data-test-selector="video-player__video-layout"]';
  const twitchSettingsLayer = '.tw-dialog-layer:has([data-a-target="player-settings-menu"])';
  const rutubePage = location.hostname === 'rutube.ru' || location.hostname.endsWith('.rutube.ru');
  const rutubePlayerSelector = 'section.video-player';
  const rutubeSettingsLayer = '[data-floating-ui-portal]:has(#raichuSettingsPanel)';
  const layoutPlayers = [youtubePlayerSelector, twitchPlayerSelector, 'vk-video-player'];
  if (location.hostname === 'player.vimeo.com') layoutPlayers.push('#player');
  if (location.hostname === 'dailymotion.com' || location.hostname.endsWith('.dailymotion.com')) {
    layoutPlayers.push('main:has(> .player.video_player)');
  }
  if (rutubePage) {
    layoutPlayers.push(rutubePlayerSelector, '[class*="touch-handlers-layout-module__layout___"]');
  }
  const layoutPlayerSelector = layoutPlayers.join(',');
  const playerContainers = [
    ...layoutPlayers, '#movie_player', '.html5-video-player', '.vp-player',
    '.video-player', '.dmp_Player', '.video-js', '.jwplayer', '.plyr--video',
    '.shaka-video-container', 'media-player', 'mux-player'
  ];
  const playerSelector = playerContainers.join(',');

  const autoPipKey = `auto-pip:${location.origin}`;
  let autoPipRegistered = false;

  async function openAutoPip() {
    if (document.pictureInPictureElement || window.documentPictureInPicture?.window || document.fullscreenElement) return;
    const scope = selected || document;
    const videos = scope instanceof HTMLVideoElement ? [scope] : scope.querySelectorAll('video');
    let candidate, largestArea = 0;
    for (const video of videos) {
      if (video.paused || video.ended || !video.videoWidth || video.disablePictureInPicture) continue;
      const {width, height} = video.getBoundingClientRect();
      const area = width * height;
      if (area > largestArea && getComputedStyle(video).visibility === 'visible') {
        candidate = video;
        largestArea = area;
      }
    }
    // Chrome grants activation to this media-session callback when the site is eligible.
    await candidate?.requestPictureInPicture().catch(() => {});
  }

  function setAutoPip(enabled) {
    if (enabled === autoPipRegistered || !navigator.mediaSession || !document.pictureInPictureEnabled ||
        location.protocol !== 'https:' || !window.isSecureContext || chrome.extension.inIncognitoContext) return;
    try {
      navigator.mediaSession.setActionHandler('enterpictureinpicture', enabled ? openAutoPip : null);
      autoPipRegistered = enabled;
    } catch {
      // Older Chrome versions do not expose this media-session action.
    }
  }

  async function refreshAutoPip() {
    const { [autoPipKey]: enabled } = await chrome.storage.local.get(autoPipKey);
    setAutoPip(enabled === true);
  }

  if (location.protocol === 'https:' && window.isSecureContext && !chrome.extension.inIncognitoContext) {
    chrome.storage.local.onChanged.addListener(changes => {
      if (changes[autoPipKey]) setAutoPip(changes[autoPipKey].newValue === true);
    });
    refreshAutoPip().catch(() => {});
  }

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
    for (const existing of roots) if (!existing.host.isConnected) roots.delete(existing);
    host.lang = SWI18n.language; roots.add(root);
    const style = document.createElement('style');
    style.textContent = `
      :host{color-scheme:dark}*{box-sizing:border-box}button,input{font:13px system-ui,sans-serif}
      button{border:1px solid #526077;background:#263349;color:#fff;border-radius:5px;padding:6px 9px;cursor:pointer;white-space:nowrap}
      button:hover{background:#3c5273}button:focus-visible,input:focus-visible{outline:2px solid #9fc5ff;outline-offset:2px}
      .bar{pointer-events:auto;position:fixed;top:0;right:0;width:max-content;max-width:100%;padding:6px;display:flex;flex-wrap:wrap;justify-content:flex-end;align-items:center;gap:5px;opacity:0;transition:opacity 120ms ease-out}
      .bar:hover,.bar:focus-within{opacity:.75}.bar:focus-within{transition:none}
      .bar button{pointer-events:none}.bar:hover button,.bar:focus-within button{pointer-events:auto}
      .bar button{background:#152031}.bar button:hover{background:#344963}
      .bar[data-tour-lesson] [data-tour-control=return],
      .bar[data-tour-lesson=video] [data-tour-control=pin],
      .bar[data-tour-lesson=chart] [data-tour-control=zoom]{border-color:#9fc5ff}
      @media(prefers-reduced-motion:reduce){.bar{transition:none}}
      .outline{position:fixed;border:3px solid #5089ff;background:#5089ff18;pointer-events:none}
      .shield{position:fixed;inset:0;pointer-events:auto;cursor:crosshair;touch-action:none;outline:none}
      .hint,.notice{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);max-width:90vw;padding:12px 18px;border-radius:8px;background:#101a2b;color:#fff;font:14px/1.5 system-ui;text-align:center;box-shadow:0 3px 15px #0005;pointer-events:auto}
      .hint button{margin-left:12px}.marker{position:fixed;pointer-events:none;opacity:0;background:#2357d9;box-shadow:0 2px 8px #0005}
      .tour-tip{bottom:54px;pointer-events:none}
      .marker.visible,.marker:focus-visible{opacity:.5;pointer-events:auto}
      dialog{pointer-events:auto;max-width:90vw;width:560px;border:1px solid #526077;border-radius:12px;background:#101a2b;color:#fff;padding:20px;font:14px system-ui}dialog::backdrop{background:#0008}dialog input{width:100%;padding:10px;margin:12px 0;color:#fff;background:#263349;border:1px solid #526077}
    `;
    root.append(style);
    document.documentElement.append(host);
    return {host, root};
  }

  function notify(text, tourTip = false) {
    if (!ui) ({host: ui, root: shadow} = makeUI());
    shadow.querySelector('.notice')?.remove();
    const node = document.createElement('div');
    node.className = 'notice'; node.setAttribute('role', 'status'); node.textContent = text;
    if (tourTip) node.classList.add('tour-tip');
    shadow.append(node); clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => {node.remove(); if (!selected && !picker) {ui?.remove(); ui = null;}}, tourTip ? 9000 : 5000);
  }

  function cssSelector(element) {
    // Known player roots may get a new framework-generated ID on each visit.
    const playerRoot = layoutPlayers.find(candidate =>
      element.matches(candidate) && document.querySelectorAll(candidate).length === 1);
    if (playerRoot) return playerRoot;
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

  function playerTarget(element) {
    const player = (rutubePage && element.closest(rutubePlayerSelector)) || element.closest(playerSelector);
    if (player && player.getClientRects().length) return player;
    if (element.closest('#player-controls')) {
      const youtube = document.querySelector(youtubePlayerSelector);
      if (youtube?.getClientRects().length) return youtube;
    }
    if (!element.matches('video') || element.controls) return element;
    // Prefer a compact custom player with sibling controls over its raw video.
    const video = element.getBoundingClientRect();
    if (!video.width || !video.height) return element;
    for (let parent = element.parentElement, depth = 0; parent && depth < 4; parent = parent.parentElement, depth++) {
      if (parent.matches('body,html')) break;
      const rect = parent.getBoundingClientRect();
      if (rect.width > video.width * 1.25 || rect.height > video.height * 1.35) break;
      const videos = parent.querySelectorAll('video');
      if (videos.length !== 1) break;
      if (parent.querySelector('button,[role="slider"],input[type="range"]')) return parent;
    }
    return element;
  }

  function consumePickerDoubleClick(element) {
    // A click just after picking can still belong to Chromium's picker click sequence.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 500);
    window.addEventListener('dblclick', event => {
      if (!event.isTrusted || selected !== element ||
          (!element.contains(event.target) && !playerControls?.contains(event.target))) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      clearTimeout(timeout);
      controller.abort();
    }, {capture: true, signal: controller.signal});
  }

  function startPicker() {
    if (selected) return;
    stopPendingSelection();
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
      if (element === picker.hit) return;
      picker.hit = element;
      const suggested = playerTarget(element);
      if (!suggested.contains(element)) element = suggested;
      picker.chain = [];
      while (element && element !== document.documentElement) {picker.chain.push(element); element = element.parentElement;}
      picker.index = Math.max(0, picker.chain.indexOf(suggested)); draw();
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
      if (element) {
        if (element.matches(playerSelector) || element.matches('video') || element.querySelector('video')) {
          consumePickerDoubleClick(element);
        }
        openElement(element, true).catch(error => notify(error.message));
      }
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
    const fitW = rotated ? h : w, fitH = rotated ? w : h;
    const factor = fit ? Math.min(availableW / fitW, availableH / fitH) * scale : scale;
    const youtube = selected.matches(youtubePlayerSelector);
    const twitch = selected.matches(twitchPlayerSelector);
    const knownPlayer = selected.matches(layoutPlayerSelector);
    const resizePlayer = initialSize.media || knownPlayer;
    // Keep native settings that these players render in a sibling portal.
    const settingsLayer = !cleanVideo && (twitch ? twitchSettingsLayer : rutubePage && knownPlayer && rutubeSettingsLayer);
    // Resizing in layout keeps embedded viewports and player controls in sync
    // with the visible size. Generic blocks keep their original layout.
    const fitted = value => fit ? `min(${100 * scale * value / fitW}vw, ${100 * scale * value / fitH}vh)` : `${value * scale}px`;
    const width = resizePlayer ? fitted(w) : `${w}px`;
    const height = resizePlayer ? fitted(h) : `${h}px`;
    const placement = resizePlayer
      ? `left:calc((100vw - ${width}) / 2)!important;top:calc((100vh - ${height}) / 2)!important;transform:rotate(${rotation}deg)!important;`
      : `left:50%!important;top:50%!important;transform:translate(-50%,-50%) rotate(${rotation}deg) scale(${factor})!important;`;
    const target = `[${targetAttr}]`, ancestor = `[${ancestorAttr}]`, host = `[data-${token}-ui]`;
    const controls = `[${playerControlsAttr}]`;
    // Dashboard renderers measure their parents. display:contents gives those
    // parents a zero-sized box and can make the site unmount the selected panel.
    const layout = initialSize.media ? '' : ancestorLayout.map((box, index) =>
      `[${ancestorAttr}="${index}"]{display:${box.display}!important;box-sizing:content-box!important;width:${box.width}px!important;height:${box.height}px!important;min-width:0!important;min-height:0!important;max-width:none!important;max-height:none!important;container-type:${box.containerType}!important}`
    ).join('\n');
    cropStyle.textContent = `
      ${ancestor}{display:contents!important;position:static!important;margin:0!important;padding:0!important;background:none!important;border:0!important;border-radius:0!important;box-shadow:none!important;outline:0!important;transform:none!important;translate:none!important;rotate:none!important;scale:none!important;zoom:1!important;filter:none!important;backdrop-filter:none!important;perspective:none!important;contain:none!important;container-type:normal!important;content-visibility:visible!important;clip:auto!important;clip-path:none!important;overflow:visible!important;opacity:1!important;isolation:auto!important;mix-blend-mode:normal!important;will-change:auto!important}
      ${ancestor}::before,${ancestor}::after{content:none!important;display:none!important}
      html${ancestor}{display:block!important;background:${cropBackground}!important}
      ${ancestor} > :not(${ancestor}):not(${target}):not(${controls}):not(${host}):not(style):not(script):not(link)${settingsLayer ? `:not(${settingsLayer})` : ''}{display:none!important}
      ${target},${controls}{position:fixed!important;inset:auto!important;width:${width}!important;height:${height}!important;min-width:0!important;min-height:0!important;max-width:none!important;max-height:none!important;margin:0!important;${placement}transform-origin:center!important;box-sizing:border-box!important;}
      ${target}{display:${initialSize.display}!important;z-index:2147483640!important;translate:none!important;rotate:none!important;scale:none!important;zoom:1!important;filter:none!important;visibility:visible!important;}
      ${target}:fullscreen{inset:0!important;width:100%!important;height:100%!important;transform:none!important}
      ${controls}{z-index:2147483641!important;translate:none!important;rotate:none!important;scale:none!important;zoom:1!important;${cleanVideo ? 'display:none!important' : ''}}
      ${host}{display:block!important}
      ${layout}
      html${ancestor},body${ancestor}{min-width:0!important;min-height:0!important;overflow:hidden!important;scrollbar-width:none!important}
      ${resizePlayer ? `
        html${ancestor},body${ancestor}{width:100%!important;height:100%!important}
        ${target},${controls}{overflow:hidden!important}
      ` : ''}
      ${youtube ? `
        ${target} .html5-video-container,${target} .html5-video-container > video.html5-main-video{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;}
        ${target} video.html5-main-video{object-fit:contain!important}
      ` : ''}
      ${twitch ? `
        ${target} :is(.video-player__container,[data-test-selector="video-player__video-container"],[data-a-target="video-ref"],[data-a-target="video-ref"] > video){position:absolute!important;inset:0!important;width:100%!important;height:100%!important;max-width:none!important;max-height:none!important}
        ${target} [data-a-target="video-ref"] > video{object-fit:contain!important}
      ` : ''}
      ${settingsLayer ? `${ancestor} > ${settingsLayer}{position:relative!important;z-index:2147483642!important}` : ''}
    `;
  }

  function unCrop(showMarker = true) {
    stopPicker();
    stopPendingSelection();
    closeBlockPreview();
    toolbarEvents?.abort();
    toolbarEvents = null;
    cropObserver?.disconnect(); cropObserver = null;
    clearTimeout(recoveryTimer); recoveryTimer = null;
    cropStyle?.remove(); cropStyle = null;
    playerControls?.removeAttribute(playerControlsAttr); playerControls = null;
    selected?.removeAttribute(targetAttr);
    for (const ancestor of ancestors) ancestor.removeAttribute(ancestorAttr);
    ancestors = []; ancestorLayout = []; selected = null; detached = false; pinButton = null; pipActive = false;
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

  function closeBlockPreview(preview = blockPreview, closeWindow = true) {
    if (!preview || blockPreview !== preview) return;
    blockPreview = null;
    clearTimeout(preview.expiry);
    preview.track?.stop();
    if (closeWindow && preview.window && !preview.window.closed) preview.window.close();
    renderPinButton();
  }

  async function withCropTimeout(operation) {
    let timeout;
    try {
      return await Promise.race([
        operation,
        new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new DOMException('Preview crop timed out', 'TimeoutError')), 5000);
        })
      ]);
    } finally {clearTimeout(timeout);}
  }

  async function cropBlockPreview(preview, element, target) {
    target ??= await withCropTimeout(CropTarget.fromElement(element));
    if (blockPreview !== preview || selected !== element) return false;
    await withCropTimeout(preview.track.cropTo(target));
    return blockPreview === preview && selected === element;
  }

  function rememberBlockPreviewSize(previewWindow) {
    if (chrome.extension.inIncognitoContext) return;
    let width = previewWindow.innerWidth, height = previewWindow.innerHeight;
    let timeout;
    function save() {
      if (timeout === undefined) return;
      clearTimeout(timeout);
      timeout = undefined;
      chrome.storage.local.set({pipPreviewSize: {width, height}}).catch(() => {});
    }
    previewWindow.addEventListener('resize', () => {
      const nextWidth = previewWindow.innerWidth, nextHeight = previewWindow.innerHeight;
      if (!nextWidth || !nextHeight || (width === nextWidth && height === nextHeight)) return;
      width = nextWidth;
      height = nextHeight;
      clearTimeout(timeout);
      timeout = setTimeout(save, 250);
    });
    previewWindow.addEventListener('pagehide', save, {once: true});
  }

  async function showBlockPreview(preview) {
    clearTimeout(preview.expiry);
    try {
      // Chrome reuses the last position in this tab when the requested size is unchanged.
      const previewWindow = await documentPictureInPicture.requestWindow(blockPreviewRequestSize);
      if (blockPreview !== preview) {previewWindow.close(); return;}
      preview.window = previewWindow;
      rememberBlockPreviewSize(previewWindow);
      previewWindow.addEventListener('pagehide', () => closeBlockPreview(preview, false), {once: true});
      previewWindow.document.title = t('pinPreviewTitle');
      previewWindow.document.documentElement.lang = SWI18n.language;
      previewWindow.document.body.style.cssText = 'margin:0;background:#000;overflow:hidden';
      const video = previewWindow.document.createElement('video');
      preview.video = video;
      video.setAttribute('aria-label', t('pinPreviewTitle'));
      video.style.cssText = 'display:block;width:100vw;height:100vh;object-fit:contain';
      video.muted = true;
      video.srcObject = new MediaStream([preview.track]);
      previewWindow.document.body.append(video);
      let playbackTimer;
      try {
        await Promise.race([
          video.play(),
          new Promise((_, reject) => {playbackTimer = setTimeout(reject, 8000);})
        ]);
      } finally {
        clearTimeout(playbackTimer);
      }
      renderPinButton();
    } catch {
      if (blockPreview !== preview) return;
      closeBlockPreview(preview);
      throw new Error(t('pinPreviewError'));
    }
  }

  async function startBlockPreview() {
    if (!window.documentPictureInPicture || !window.CropTarget || !navigator.mediaDevices?.getDisplayMedia) {
      throw new Error(t('pinPreviewUnavailable'));
    }
    const chromium = Number(navigator.userAgent.match(/Chrome\/(\d+)/)?.[1]);
    // Older Windows Chromium builds can crash on stopping a tab capture.
    if (/^Win/i.test(navigator.userAgentData?.platform || navigator.platform) && chromium && chromium < 156) {
      throw new Error(t('pinPreviewUpdateChrome'));
    }
    const preview = {};
    blockPreview = preview;
    const savedSize = !blockPreviewRequestSize && !chrome.extension.inIncognitoContext
      ? chrome.storage.local.get('pipPreviewSize').then(settings => settings.pipPreviewSize).catch(() => undefined)
      : undefined;
    const element = selected;
    let target;
    try {
      target = await withCropTimeout(CropTarget.fromElement(element));
    } catch {
      if (blockPreview !== preview) return;
      closeBlockPreview(preview);
      throw new Error(t('pinPreviewCropTimeout'));
    }
    if (blockPreview !== preview) return;
    if (selected !== element || !navigator.userActivation.isActive) {
      closeBlockPreview(preview);
      throw new Error(t('pinPreviewError'));
    }
    let stream;
    notify(t('pinChooseTab'));
    try {
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: {displaySurface: 'browser', frameRate: {ideal: 120}},
        audio: false, preferCurrentTab: true,
        selfBrowserSurface: 'include', surfaceSwitching: 'exclude', monitorTypeSurfaces: 'exclude'
      });
    } catch {
      if (blockPreview !== preview) return;
      closeBlockPreview(preview);
      throw new Error(t('pinShareError'));
    }
    const [track] = stream.getVideoTracks();
    if (blockPreview !== preview) {
      track?.stop();
      return;
    }
    preview.track = track;
    try {
      if (track?.getSettings().displaySurface !== 'browser' || !track.cropTo) throw new Error();
      // Chrome accepts this element as the crop target only for capture of its own tab.
      let cropped = await cropBlockPreview(preview, selected, selected === element ? target : undefined);
      if (!cropped && blockPreview === preview) cropped = await cropBlockPreview(preview, selected);
      if (!cropped || track.readyState !== 'live') throw new Error();
      preview.cropped = true;
    } catch (error) {
      if (blockPreview !== preview) return;
      closeBlockPreview(preview);
      throw new Error(t(error?.name === 'TimeoutError' ? 'pinPreviewCropTimeout' : 'pinWrongTab'));
    }
    if (blockPreview !== preview) return;
    track.addEventListener('ended', () => closeBlockPreview(preview), {once: true});
    const size = await savedSize;
    if (blockPreview !== preview) return;
    blockPreviewRequestSize ||= Number.isSafeInteger(size?.width) && size.width > 0 &&
      Number.isSafeInteger(size?.height) && size.height > 0
      ? size
      : {width: Math.round(initialSize.width), height: Math.round(initialSize.height)};
    clearTimeout(noticeTimer);
    shadow?.querySelector('.notice')?.remove();
    if (navigator.userActivation.isActive) {
      await showBlockPreview(preview);
    } else {
      preview.expiry = setTimeout(() => closeBlockPreview(preview), 30000);
      renderPinButton();
      notify(t('pinPreviewContinueHint'));
    }
  }

  window.addEventListener('pagehide', () => closeBlockPreview());

  function toolbar() {
    ({host: ui, root: shadow} = makeUI());
    toolbarEvents = new AbortController();
    const bar = document.createElement('div'); bar.className = 'bar'; bar.setAttribute('aria-label', t('controls'));
    bar.addEventListener('pointerleave', () => {
      const focused = shadow?.activeElement;
      if (focused && bar.contains(focused)) focused.blur();
    });
    bar.addEventListener('keydown', event => {
      if (event.key === 'Escape') {shadow.activeElement?.blur(); event.stopPropagation();}
    });
    function button(text, title, action) {
      const button = document.createElement('button'); button.textContent = text; button.title = title;
      button.setAttribute('aria-label', title);
      button.onclick = async () => {if (button.disabled) return; button.disabled = true; try {await action(button); renderCrop();} catch (error) {notify(error.message);} finally {button.disabled = false;}};
      bar.append(button);
      return button;
    }
    button(t('returnShort'), t('returnTitle'), () => send('restore')).dataset.tourControl = 'return';
    button(t('onlyVideo'), t('onlyVideo'), async button => {
      const enabled = !cleanVideo;
      await send('clean-media', {selector: `[${targetAttr}]`, frameRoots: mediaFrameRoots(), enabled});
      cleanVideo = enabled;
      button.textContent = t(enabled ? 'showPlayer' : 'onlyVideo');
      button.title = button.textContent; button.setAttribute('aria-label', button.title);
    });
    pinButton = button(t('pin'), t('pinTitle'), async () => {
      if (blockPreview?.window) {closeBlockPreview(); return;}
      if (blockPreview?.track) {await showBlockPreview(blockPreview); return;}
      const result = await send('video-pin', {selector: `[${targetAttr}]`});
      if (result.found) setPinState(result.active);
      else if (selected && detached) {
        if (selected.matches(playerSelector)) throw new Error(t('pipNoVideo'));
        await startBlockPreview();
      }
    });
    pinButton.dataset.tourControl = 'pin';
    setPinState(pipActive);
    button(t('size'), t('sizeTitle'), async button => {
      const result = await send('bounds'); button.textContent = result.saved ? t('sizeSaved') : t('size');
      notify(result.saved ? t('sizeSavedNotice') : t('sizeForgottenNotice'));
    });
    button('−', t('zoomOut'), () => {scale = Math.max(.1, scale - .1); renderCrop();}).dataset.tourControl = 'zoom';
    button('+', t('zoomIn'), () => {scale = Math.min(5, scale + .1); renderCrop();}).dataset.tourControl = 'zoom';
    button(t('fit'), t('fitTitle'), button => {fit = !fit; scale = 1; button.textContent = fit ? t('fit') : '1:1'; renderCrop();}).dataset.tourControl = 'zoom';
    button('↻', t('rotateTitle'), () => {rotation = (rotation + 90) % 360; renderCrop();});
    // Keep page shortcuts away from the link dialog.
    window.addEventListener('keydown', event => {
      const dialog = shadow.querySelector('dialog[open]');
      if (!dialog) return;
      event.stopImmediatePropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        dialog.close();
      }
    }, {capture: true, signal: toolbarEvents.signal});
    button(t('snapshot'), t('snapshotTitle'), screenshot);
    button('★', t('bookmarkTitle'), async () => {await send('bookmark', {url: windowLink()}); notify(t('bookmarkSaved'));});
    button(t('link'), t('linkTitle'), async () => {
      const dialog = document.createElement('dialog');
      const text = document.createElement('div'); text.textContent = t('linkHelp');
      const input = document.createElement('input'); input.readOnly = true; input.value = windowLink(); input.setAttribute('aria-label', t('blockLink'));
      const close = document.createElement('button'); close.textContent = t('close'); close.onclick = () => dialog.close();
      dialog.addEventListener('close', () => dialog.remove(), {once: true});
      dialog.append(text, input, close); shadow.append(dialog); dialog.showModal(); input.focus(); input.select();
    });
    button('⛶', t('fullscreen'), () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen());
    shadow.append(bar);
  }

  function setPinState(active) {
    pipActive = active;
    renderPinButton();
  }

  function renderPinButton() {
    if (!pinButton) return;
    const active = pipActive || !!blockPreview?.window;
    const ready = !active && !!blockPreview?.track;
    pinButton.textContent = t(active ? 'unpin' : ready ? 'pinPreviewContinue' : 'pin');
    pinButton.title = t(active ? 'unpinTitle' : ready ? 'pinPreviewContinueTitle' : 'pinTitle');
    pinButton.setAttribute('aria-label', pinButton.title);
    pinButton.setAttribute('aria-pressed', String(active));
  }

  function returnWithoutSelection() {
    if (selected && cleanVideo) {
      send('clean-media', {selector: `[${targetAttr}]`, frameRoots: [], enabled: false}).catch(() => {});
    }
    unCrop(false);
    detached = true;
    const {host, root} = makeUI();
    ui = host; shadow = root;
    const notice = document.createElement('div');
    notice.className = 'hint';
    notice.setAttribute('role', 'status');
    notice.textContent = t('blockNotFound');
    const restore = document.createElement('button');
    restore.textContent = t('returnShort');
    restore.onclick = () => send('restore').catch(error => notify(error.message));
    notice.append(restore);
    root.append(notice);
  }

  async function openElement(element, exact = false) {
    if (selected) return;
    if (!exact) element = playerTarget(element);
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height) throw new Error(t('hiddenBlock'));
    selector = cssSelector(element); savedSelector = selector; sourceUrl = location.href;
    initialSize = {width: rect.width, height: rect.height, display: getComputedStyle(element).display, media: element.matches('video,iframe,frame')};
    selected = element; scale = 1; rotation = 0; fit = true;
    removeMarker(); ui?.remove(); selected.setAttribute(targetAttr, '');
    markAncestors();
    syncPlayerControls();
    cropStyle = document.createElement('style'); document.documentElement.append(cropStyle);
    cleanVideo = false; toolbar(); renderCrop();
    cropObserver = new MutationObserver(() => {
      const connected = selected?.isConnected;
      const sameParents = connected && selected.parentElement === ancestors[0] &&
        ancestors.every((element, index) => element.parentElement === (ancestors[index + 1] || null));
      if (sameParents) {syncPlayerControls(); return;}
      // Frameworks can replace a panel on refresh. Follow its original selector
      // without reparenting/cloning nodes or reloading the live document.
      const replacement = connected ? selected : document.querySelector(selector);
      if (!replacement) {
        if (!recoveryTimer) recoveryTimer = setTimeout(returnWithoutSelection, 3000);
        return;
      }
      clearTimeout(recoveryTimer); recoveryTimer = null;
      // The crop hides newly inserted, unmarked ancestors. Measure them with
      // the page's layout restored, then reapply crop before the next paint.
      cropStyle.disabled = true;
      selected?.removeAttribute(targetAttr);
      for (const ancestor of ancestors) ancestor.removeAttribute(ancestorAttr);
      selected = replacement; selected.setAttribute(targetAttr, '');
      markAncestors(); syncPlayerControls(); renderCrop();
      cropStyle.disabled = false;
      if (cleanVideo && detached) {
        send('clean-media', {selector: `[${targetAttr}]`, frameRoots: mediaFrameRoots()}).catch(error => notify(error.message));
      }
      if (blockPreview?.cropped) {
        const preview = blockPreview;
        cropBlockPreview(preview, replacement).catch(() => {
          if (blockPreview !== preview || selected !== replacement) return;
          closeBlockPreview(preview);
          notify(t('pinPreviewError'));
        });
      }
    });
    cropObserver.observe(document.documentElement, {childList:true, subtree:true});
    try {
      await send('detach', {selector, width: rect.width, height: rect.height}); detached = true;
      if (tourPage && selected === element) {
        const tips = {video: 'tourVideoTip', chart: 'tourChartTip', game: 'tourGameTip'};
        const example = element.dataset.tourExample;
        tourExample = Object.hasOwn(tips, example) ? example : 'other';
        shadow.querySelector('.bar').dataset.tourLesson = tourExample;
        document.documentElement.setAttribute(tourStateAttr, 'open:' + tourExample);
        notify(t(tips[tourExample] || 'tourReturnTip'), true);
      }
    }
    catch (error) {unCrop(); throw error;}
  }

  function markAncestors() {
    const previous = new Map(ancestors.map((node, index) => [node, ancestorLayout[index]]));
    ancestors = []; ancestorLayout = [];
    for (let node = selected.parentElement; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      const box = previous.get(node) || {
        display: style.display === 'contents' ? 'block' : style.display,
        width: Math.max(0, node.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)),
        height: Math.max(0, node.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom)),
        containerType: style.containerType
      };
      node.setAttribute(ancestorAttr, String(ancestors.length));
      ancestors.push(node); ancestorLayout.push(box);
    }
    cropBackground = readCropBackground();
  }

  function readCropBackground() {
    if (initialSize.media || selected.matches(playerSelector)) return '#000';
    const layers = [];
    for (const ancestor of ancestors) {
      const color = getComputedStyle(ancestor).backgroundColor;
      if (color.startsWith('rgb(')) return layers.concat(color).join(', ');
      if (color !== 'rgba(0, 0, 0, 0)') layers.push(`linear-gradient(${color}, ${color})`);
    }
    // Solid layers retain translucent tints while the rest of the page is hidden.
    return layers.concat('Canvas').join(', ');
  }

  function syncPlayerControls() {
    // YouTube can mount its HUD next to the video container as a separate layer.
    if (!playerControls && !selected?.matches(youtubePlayerSelector)) return;
    const portal = document.getElementById('player-controls');
    const next = selected?.matches(youtubePlayerSelector) && portal &&
      ancestors.includes(portal.parentElement) ? portal : null;
    if (next === playerControls) return;
    playerControls?.removeAttribute(playerControlsAttr);
    playerControls = next;
    playerControls?.setAttribute(playerControlsAttr, '');
  }

  function mediaFrameRoots() {
    return [...document.querySelectorAll('iframe,frame')].filter(frame => selected.contains(frame)).map(frame => {
      for (let index = 0; index < window.length; index++) if (window[index] === frame.contentWindow) return String(index);
    }).filter(root => root !== undefined);
  }

  function positionMarker() {
    if (!marker || !markerTarget?.isConnected) return;
    const rect = markerTarget.getBoundingClientRect();
    marker.style.left = `${Math.max(0, rect.left)}px`; marker.style.top = `${Math.max(0, rect.top)}px`;
    marker.hidden = rect.bottom < 0 || rect.top > innerHeight || !rect.width || !rect.height;
  }
  function removeMarker() {
    markerEvents?.abort(); markerEvents = null;
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
    marker.setAttribute('aria-label', t('marker'));
    markerTarget = element; marker.onclick = () => openElement(element).catch(error => notify(error.message));
    markerEvents = new AbortController();
    const options = {signal: markerEvents.signal};
    const update = () => marker?.classList.toggle('visible', markerTarget.matches(':hover') || marker.matches(':hover'));
    element.addEventListener('mouseenter', () => marker?.classList.add('visible'), options);
    element.addEventListener('mouseleave', event => {
      if (event.relatedTarget !== root.host && !marker?.matches(':hover')) marker?.classList.remove('visible');
    }, options);
    marker.addEventListener('mouseenter', () => marker?.classList.add('visible'), options);
    marker.addEventListener('mouseleave', update, options);
    window.addEventListener('blur', () => marker?.classList.remove('visible'), options);
    root.append(marker); positionMarker(); update(); return true;
  }

  window.addEventListener('resize', () => {renderCrop(); positionMarker();});
  window.addEventListener('scroll', positionMarker, {passive: true, capture: true});
  document.addEventListener('load', event => {
    if (selected && cleanVideo && event.target.localName === 'iframe' && selected.contains(event.target)) {
      send('clean-media', {selector: `[${targetAttr}]`, frameRoots: mediaFrameRoots()}).catch(error => notify(error.message));
    }
  }, true);
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (sender.id !== chrome.runtime.id) return;
    switch (message.type) {
      case 'select':
        Promise.all([SWI18n.ready, documentReady]).then(startPicker)
          .then(() => respond({ok: true}), error => respond({ok: false, error: error.message}));
        return true;
      case 'uncrop': unCrop(false); break;
      case 'auto-pip-refresh':
        refreshAutoPip().then(() => respond({ok: true}), error => respond({ok: false, error: error.message}));
        return true;
      case 'pip-state': setPinState(message.active); break;
      case 'returned':
        detached = false; installMarker(savedSelector);
        if (tourPage && tourExample) {
          document.documentElement.setAttribute(tourStateAttr, 'returned:' + tourExample);
          tourExample = undefined;
        }
        break;
      default: return;
    }
    respond({ok: true});
  });

  function stopPendingSelection() {
    selectionGeneration++;
    selectionObserver?.disconnect(); selectionObserver = null;
    clearTimeout(selectionTimer);
  }

  async function init(requestedUrl) {
    stopPendingSelection();
    const generation = selectionGeneration;
    const request = new URL(requestedUrl);
    const linkHash = request.hash.startsWith('#__sw_local=') ? request.hash : '';
    const context = await send('window-state');
    if (generation !== selectionGeneration || selected || picker) return;
    if (linkHash && (request.origin !== location.origin || request.pathname !== location.pathname || request.search !== location.search)) return;
    detached = context.detached;
    let automatic = false;
    if (linkHash) {
      try {
        const data = JSON.parse(decodeURIComponent(linkHash.slice(12)));
        if (typeof data.selector !== 'string' || data.selector.length > 12000 || typeof data.hash !== 'string' || (data.hash && !data.hash.startsWith('#'))) throw new Error(t('invalidBlockLink'));
        savedSelector = data.selector; automatic = true;
        if (location.hash === linkHash) history.replaceState(history.state, '', location.pathname + location.search + data.hash);
      } catch (error) {notify(t('linkError', error.message)); return;}
    } else if (!context.incognito) {
      const key = `selection:${location.href}`;
      savedSelector = (await chrome.storage.local.get(key))[key]?.selector;
    }
    if (generation !== selectionGeneration || selected || picker) return;
    if (detached) {savedSelector ||= context.selector; automatic = true;}
    if (!savedSelector) {
      if (detached) returnWithoutSelection();
      return;
    }
    function attempt() {
      let element;
      try {element = document.querySelector(savedSelector);} catch {return true;}
      if (!element || !element.getBoundingClientRect().width) return false;
      if (automatic) openElement(element).catch(error => notify(error.message));
      else installMarker(savedSelector);
      return true;
    }
    if (attempt()) return;
    selectionObserver = new MutationObserver(() => {if (attempt()) stopPendingSelection();});
    selectionObserver.observe(document.documentElement, {childList: true, subtree: true});
    selectionTimer = setTimeout(() => {
      stopPendingSelection();
      if (automatic && !selected) {
        if (detached) returnWithoutSelection();
        else notify(t('blockNotFound'));
      }
    }, 15000);
  }
  // A site's router can clear the link hash before we read the current address.
  const ready = documentReady.then(() => SWI18n.ready);
  window.addEventListener('hashchange', event => {
    if (!event.isTrusted || selected || !new URL(event.newURL).hash.startsWith('#__sw_local=')) return;
    ready.then(() => init(event.newURL)).catch(error => notify(error.message));
  });
  ready.then(() => {
    if (tourPage) document.documentElement.setAttribute(tourStateAttr, 'ready');
    if (!selectionGeneration) return init(initialUrl);
  }).catch(error => notify(error.message));
})();
