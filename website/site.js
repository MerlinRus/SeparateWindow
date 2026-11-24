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

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const disclosureEasing = getComputedStyle(document.documentElement).getPropertyValue('--ease-out').trim() || 'ease-out';

function animateDisclosure(details, content, onOpen) {
  const summary = details.querySelector('summary');
  let animation;
  let opening;

  function settle(open) {
    details.open = open;
    details.removeAttribute('data-closing');
    content.inert = false;
    animation?.cancel();
    animation = undefined;
    if (open) onOpen?.();
  }

  summary.addEventListener('click', event => {
    const nextOpen = animation ? !opening : !details.open;
    if (reducedMotion.matches || !content.animate) {
      if (animation || onOpen) {
        event.preventDefault();
        settle(nextOpen);
      }
      return;
    }

    event.preventDefault();
    // Read the visible height before cancelling so a second click reverses in place.
    const from = details.open ? content.getBoundingClientRect().height : 0;
    animation?.cancel();
    details.open = true;
    opening = nextOpen;
    details.toggleAttribute('data-closing', !opening);
    content.inert = !opening;
    const naturalHeight = content.getBoundingClientRect().height;
    const to = opening ? naturalHeight : 0;
    if (Math.abs(to - from) < 1) {
      settle(opening);
      return;
    }

    const duration = 200 * Math.min(1, Math.abs(to - from) / naturalHeight);
    const current = content.animate([{height: `${from}px`}, {height: `${to}px`}], {
      duration, easing: disclosureEasing, fill: 'both',
    });
    animation = current;
    current.onfinish = () => {
      if (animation === current) settle(nextOpen);
    };
  });
}

for (const details of document.querySelectorAll('.answers details')) {
  animateDisclosure(details, details.querySelector('.faq-answer'));
}
const footerSupport = document.querySelector('.footer-support');
animateDisclosure(footerSupport, footerSupport.querySelector('.footer-support-body'), () => {
  footerSupport.scrollIntoView({block: 'nearest', behavior: reducedMotion.matches ? 'instant' : 'smooth'});
});

if (!reducedMotion.matches && 'IntersectionObserver' in window) {
  const reveal = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-in-view');
      reveal.unobserve(entry.target);
    }
  }, {threshold: 0.15});
  document.querySelectorAll('[data-reveal]').forEach(section => reveal.observe(section));
}
