function render() {
  document.documentElement.lang = SWI18n.language;
  for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = SWI18n.t(element.dataset.i18n);
  for (const element of document.querySelectorAll('[data-i18n-label]')) element.setAttribute('aria-label', SWI18n.t(element.dataset.i18nLabel));
  document.querySelector('#language').value = SWI18n.preference;
  document.querySelector('#version').textContent = chrome.runtime.getManifest().version;
}
SWI18n.onChange(old => {
  render(); const status = document.querySelector('#status'); status.textContent = SWI18n.translate(status.textContent, old);
});
SWI18n.ready.then(render);
document.querySelector('#language').addEventListener('change', async event => {
  const select = event.target; select.disabled = true;
  try {await chrome.storage.local.set({language:select.value}); await SWI18n.reload(); render();}
  catch (error) {document.querySelector('#status').textContent = error.message;}
  finally {select.disabled = false;}
});

for (const button of document.querySelectorAll('button')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await SWI18n.ready;
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      if (!tab) throw new Error(SWI18n.t('noActiveTab'));
      const result = await chrome.runtime.sendMessage({type: button.id, tabId: tab.id});
      if (!result?.ok) throw new Error(result?.error || SWI18n.t('commandFailed'));
      window.close();
    } catch (error) {
      document.querySelector('#status').textContent = error.message;
      button.disabled = false;
    }
  });
}
