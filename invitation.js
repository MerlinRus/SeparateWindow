(() => {
  const dialog = document.querySelector('#onboarding-invite');
  const welcome = document.body.classList.contains('welcome');
  const welcomeStart = welcome ? document.querySelector('[data-onboarding-choice="start"]') : null;
  const choices = [...document.querySelectorAll('[data-onboarding-choice]')];
  let busy = false;

  function localize() {
    if (welcome) document.documentElement.lang = SWI18n.language;
    for (const element of document.querySelectorAll('[data-onboarding-copy]')) {
      element.textContent = SWI18n.t(element.dataset.onboardingCopy);
    }
  }

  function showInvitation(state) {
    if (dialog) {
      if (state === 'pending' && !dialog.open) dialog.showModal();
      if (state !== 'pending' && dialog.open) dialog.close();
    } else if (welcomeStart) {
      welcomeStart.dataset.onboardingChoice = state === 'pending' ? 'start' : 'replay';
    }
  }

  async function choose(button) {
    if (busy) return;
    busy = true;
    const status = button.closest('.onboarding-invite')?.querySelector('.onboarding-status') ??
      document.querySelector('#status');
    status.textContent = '';
    try {
      const response = await chrome.runtime.sendMessage({type: 'onboarding', choice: button.dataset.onboardingChoice});
      if (!response?.ok) throw new Error(response?.error || SWI18n.t('commandFailed'));
      if (welcome) {
        const tab = await chrome.tabs.getCurrent();
        if (tab) await chrome.tabs.remove(tab.id);
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      busy = false;
    }
  }

  for (const button of choices) button.addEventListener('click', () => choose(button));
  dialog?.addEventListener('cancel', event => {
    event.preventDefault();
    choose(dialog.querySelector('[data-onboarding-choice="skip"]'));
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.onboarding) showInvitation(changes.onboarding.newValue);
  });
  SWI18n.onChange(localize);
  SWI18n.ready.then(async () => {
    localize();
    showInvitation((await chrome.storage.local.get('onboarding')).onboarding);
  }).catch(console.error);
})();
