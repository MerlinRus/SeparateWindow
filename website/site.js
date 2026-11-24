const demo = document.querySelector('.demo');
const selected = document.getElementById('selected-block');
const originalSlot = document.getElementById('source-slot');
const floatingSlot = document.getElementById('float-slot');
const moveButton = document.getElementById('move-block');
const status = document.getElementById('demo-status');
const labels = document.body.dataset;
const choices = [...demo.querySelectorAll('[data-scene-button]')];

for (const choice of choices) {
  choice.addEventListener('click', () => {
    demo.dataset.scene = choice.dataset.sceneButton;
    for (const button of choices) {
      button.setAttribute('aria-pressed', String(button === choice));
    }
  });
}

moveButton.addEventListener('click', () => {
  const floating = demo.dataset.floating === 'false';
  demo.dataset.floating = String(floating);
  (floating ? floatingSlot : originalSlot).append(selected);
  moveButton.textContent = floating ? labels.restore : labels.detach;
  status.textContent = floating ? labels.detached : labels.restored;
});

const footerSupport = document.querySelector('.footer-support');
footerSupport.addEventListener('toggle', () => {
  if (footerSupport.open) footerSupport.scrollIntoView({block: 'nearest'});
});

if (window.matchMedia('(prefers-reduced-motion: no-preference)').matches && 'IntersectionObserver' in window) {
  const reveal = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-in-view');
      reveal.unobserve(entry.target);
    }
  }, {threshold: 0.15});
  document.querySelectorAll('[data-reveal]').forEach(section => reveal.observe(section));
}
