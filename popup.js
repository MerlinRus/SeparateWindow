document.documentElement.lang = chrome.i18n.getUILanguage().startsWith('ru') ? 'ru' : 'en';
for (const element of document.querySelectorAll('[data-i18n]')) element.textContent = chrome.i18n.getMessage(element.dataset.i18n);
for (const element of document.querySelectorAll('[data-i18n-label]')) element.setAttribute('aria-label', chrome.i18n.getMessage(element.dataset.i18nLabel));
document.querySelector('#version').textContent = chrome.runtime.getManifest().version;

for (const button of document.querySelectorAll('button')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      const result = await chrome.runtime.sendMessage({type: button.id, tabId: tab.id});
      if (!result?.ok) throw new Error(result?.error || chrome.i18n.getMessage('commandFailed'));
      window.close();
    } catch (error) {
      document.querySelector('#status').textContent = error.message;
      button.disabled = false;
    }
  });
}
