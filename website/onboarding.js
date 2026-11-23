const examples = ['video', 'chart', 'game'];
const stateAttr = 'data-separate-window-tour';
const progressKey = 'separate-window-tour';
const copy = document.querySelector('#tour-copy').dataset;
const workspace = document.querySelector('#tour-workspace');
const complete = document.querySelector('#tour-complete');
const heading = document.querySelector('#tour-guide-heading');
const videoStart = document.querySelector('#tour-video-start');
const instruction = document.querySelector('#tour-instruction');
const returnHint = document.querySelector('#tour-return-hint');
const status = document.querySelector('#tour-status');
const install = document.querySelector('#tour-install');
const next = document.querySelector('#tour-next');
const skip = document.querySelector('#tour-skip');
const video = document.querySelector('#practice-video');

let step = 0;
let practiced = false;
let wrongBlock = false;
try {
  const saved = JSON.parse(sessionStorage.getItem(progressKey));
  if (Number.isInteger(saved?.step) && saved.step >= 0 && saved.step <= examples.length) {
    step = saved.step;
    practiced = saved.practiced === true;
  }
} catch {}

function saveProgress() {
  try { sessionStorage.setItem(progressKey, JSON.stringify({step, practiced})); } catch {}
}

function render() {
  const active = examples[step];
  workspace.hidden = !active;
  complete.hidden = !!active;
  if (!active) return;

  for (const item of document.querySelectorAll('[data-tour-step]')) {
    if (item.dataset.tourStep === active) item.setAttribute('aria-current', 'step');
    else item.removeAttribute('aria-current');
  }
  for (const scene of document.querySelectorAll('[data-tour-scene]')) {
    scene.hidden = scene.dataset.tourScene !== active;
  }
  heading.textContent = copy[active + 'Title'];
  instruction.textContent = copy[active + 'Tip'];
  const videoStep = active === 'video';
  videoStart.hidden = !videoStep;
  returnHint.hidden = !videoStep;
  status.hidden = !practiced && !wrongBlock;
  status.textContent = practiced ? copy.returned : wrongBlock ? copy.wrongBlock : '';
  status.dataset.kind = practiced ? 'success' : 'retry';
  install.hidden = document.documentElement.hasAttribute(stateAttr);
  next.hidden = !practiced;
  skip.hidden = practiced;
}

function goTo(index) {
  if (index !== 0) video.pause();
  step = index;
  practiced = false;
  wrongBlock = false;
  saveProgress();
  render();
  (step < examples.length ? heading : document.querySelector('#complete-heading')).focus();
}

next.addEventListener('click', () => goTo(step + 1));
skip.addEventListener('click', () => goTo(step + 1));
document.querySelector('#tour-restart').addEventListener('click', () => {
  resetGame();
  goTo(0);
});

function updateFromExtension() {
  const state = document.documentElement.getAttribute(stateAttr);
  if (state?.startsWith('returned:') && step < examples.length) {
    if (state === 'returned:' + examples[step]) {
      practiced = true;
      saveProgress();
    } else if (!practiced) wrongBlock = true;
  }
  render();
}
new MutationObserver(updateFromExtension).observe(document.documentElement, {attributes: true, attributeFilter: [stateAttr]});
updateFromExtension();

const grid = document.querySelector('#game-grid');
const gameStatus = document.querySelector('#game-status');
const side = 5;
const total = side * side;
const tiles = Array.from({length: total}, (_, index) => {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'game-tile';
  button.addEventListener('click', () => reveal(index));
  return button;
});
grid.append(...tiles);
let mines, opened, finished;

function resetGame() {
  mines = null;
  opened = new Set();
  finished = false;
  gameStatus.textContent = copy.gameStart;
  for (const [index, tile] of tiles.entries()) {
    tile.removeAttribute('data-open');
    tile.removeAttribute('data-mine');
    tile.removeAttribute('aria-disabled');
    tile.setAttribute('aria-label', copy.tile + ' ' + (index + 1));
    tile.textContent = '';
  }
}

function neighbors(index) {
  const x = index % side;
  const y = Math.floor(index / side);
  const result = [];
  for (let row = Math.max(0, y - 1); row <= Math.min(side - 1, y + 1); row++) {
    for (let col = Math.max(0, x - 1); col <= Math.min(side - 1, x + 1); col++) {
      if (row !== y || col !== x) result.push(row * side + col);
    }
  }
  return result;
}

function reveal(index) {
  if (finished || opened.has(index)) return;
  mines ??= new Set([5, 9, 14, 21].map(offset => (index + offset) % total));
  if (mines.has(index)) {
    finished = true;
    gameStatus.textContent = copy.gameLost;
    for (const mine of mines) {
      tiles[mine].setAttribute('data-open', '');
      tiles[mine].setAttribute('data-mine', '');
      tiles[mine].setAttribute('aria-label', copy.mine);
      tiles[mine].textContent = '✹';
    }
    return;
  }

  const pending = [index];
  while (pending.length) {
    const tileIndex = pending.pop();
    if (opened.has(tileIndex)) continue;
    opened.add(tileIndex);
    const nearby = neighbors(tileIndex);
    const count = nearby.filter(adjacent => mines.has(adjacent)).length;
    const tile = tiles[tileIndex];
    tile.setAttribute('data-open', '');
    tile.setAttribute('aria-disabled', 'true');
    tile.setAttribute('aria-label', copy.tile + ' ' + (tileIndex + 1) + ' · ' + count);
    tile.textContent = count || '';
    if (!count) pending.push(...nearby);
  }
  finished = opened.size === total - mines.size;
  gameStatus.textContent = finished ? copy.gameWon : copy.gamePlay;
}

document.querySelector('#game-reset').addEventListener('click', resetGame);
resetGame();
