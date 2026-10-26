for (const button of document.querySelectorAll('button')) {
  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
      const result = await chrome.runtime.sendMessage({type: button.id, tabId: tab.id});
      if (!result?.ok) throw new Error(result?.error || 'Не удалось выполнить команду.');
      window.close();
    } catch (error) {
      document.querySelector('#status').textContent = error.message;
      button.disabled = false;
    }
  });
}
