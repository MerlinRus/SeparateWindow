globalThis.SWI18n ??= (() => {
  let messages = {}, language, preference = 'auto', pending, generation = 0;
  const listeners = new Set(), dictionaries = new Map();
  const content = typeof location !== 'undefined' && location.protocol !== 'chrome-extension:';
  function t(key, substitutions) {
    const values = Array.isArray(substitutions) ? substitutions : [substitutions ?? ''];
    return (messages[key]?.message ?? chrome.i18n.getMessage(key)).replace(/\$(\d+)/g, (_, n) => values[Number(n)-1] ?? '');
  }
  async function load(request) {
    let next;
    if (content) {
      const response = await chrome.runtime.sendMessage({type:'translations'});
      if (!response?.ok) throw new Error(response?.error || chrome.i18n.getMessage('unavailable'));
      next = response;
    } else {
      const saved = (await chrome.storage.local.get('language')).language;
      const pref = ['ru','en'].includes(saved) ? saved : 'auto';
      const lang = pref === 'auto' ? (chrome.i18n.getUILanguage().startsWith('ru') ? 'ru' : 'en') : pref;
      if (!dictionaries.has(lang)) dictionaries.set(lang, fetch(chrome.runtime.getURL(`_locales/${lang}/messages.json`)).then(response => {
        if (!response.ok) throw new Error('Unable to load translations');
        return response.json();
      }));
      next = {language:lang, preference:pref, messages:await dictionaries.get(lang)};
    }
    if (request !== generation) return pending;
    const old = messages, changed = language !== next.language || preference !== next.preference;
    messages = next.messages; language = next.language; preference = next.preference;
    if (changed) for (const listener of listeners) listener(old);
  }
  function reload() {return pending = load(++generation);}
  function translate(text, old) {
    for (const [key, value] of Object.entries(old)) {
      if (text === value.message) return t(key);
      if (value.message.includes('$1')) {
        const [before, after] = value.message.split('$1');
        if (text.startsWith(before) && text.endsWith(after)) return t(key, text.slice(before.length, after ? -after.length : undefined));
      }
    }
    return text;
  }
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.language) reload().catch(console.error);
  });
  reload().catch(console.error);
  return {t, translate, reload, onChange:listener => listeners.add(listener), get ready(){return pending;},
    get language(){return language;}, get preference(){return preference;}, get messages(){return messages;}};
})();
