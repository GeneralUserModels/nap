async function init() {
  let examples;
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/demo2/examples.json`);
    if (!res.ok) {
      console.error('Demo 2: Failed to fetch examples.json:', res.status);
      return;
    }
    examples = await res.json();
  } catch (e) {
    console.error('Demo 2: Error loading examples:', e);
    return;
  }

  const grid = document.getElementById('predictions-grid');
  if (!grid || !examples.length) return;

  examples.forEach((ex, i) => {
    const card = document.createElement('div');
    card.className = 'pred-card';
    card.style.opacity = '1';

    const screenshot = ex.screenshots?.[0]
      ? `<img class="pred-card__screenshot" src="${import.meta.env.BASE_URL + ex.screenshots[0].replace(/^\//, '')}" alt="Screenshot" loading="lazy" />`
      : '';

    const predicted = (ex.predicted_actions || [])
      .map(a => `<li>${escapeHtml(a)}</li>`).join('');

    const trueLabels = (ex.true_labels || [])
      .map(a => `<li>${escapeHtml(a)}</li>`).join('');

    const reasoning = '';

    card.innerHTML = `
      <div class="pred-card__header">
        <span class="pred-card__time">${ex.time_range || ''}</span>
        <span class="pred-card__utility">Reward: ${(ex.utility || 0).toFixed(2)}</span>
      </div>
      <div class="pred-card__body">
        ${screenshot}
        <div class="pred-card__columns">
          <div>
            <p class="pred-card__col-label">Predicted Actions</p>
            <ul class="pred-card__actions pred-card__actions--predicted">${predicted}</ul>
          </div>
          <div>
            <p class="pred-card__col-label">Actual Actions</p>
            <ul class="pred-card__actions pred-card__actions--true">${trueLabels}</ul>
          </div>
        </div>
        ${reasoning}
      </div>
    `;

    try {
      grid.appendChild(card);
    } catch (e) {
      console.error(`Demo 2: Error rendering card ${i}:`, e);
    }
  });

  // --- Cap action list heights to screenshot height ---
  function applyScrollLimits(card) {
    const img = card.querySelector('.pred-card__screenshot');
    const lists = card.querySelectorAll('.pred-card__actions');
    if (!img || !lists.length) return;

    const apply = () => {
      const imgH = img.offsetHeight;
      if (imgH <= 0) return;
      const maxH = Math.floor(imgH / 2) - 24;
      lists.forEach(ul => {
        ul.style.maxHeight = maxH + 'px';
        ul.style.overflowY = 'scroll';
      });
    };

    if (img.complete) apply();
    else img.addEventListener('load', apply);
  }

  window.addEventListener('resize', () => {
    grid.querySelectorAll('.pred-card.active').forEach(applyScrollLimits);
  });

  // --- Carousel logic ---
  const cards = grid.querySelectorAll('.pred-card');
  const total = cards.length;
  if (total === 0) return;

  let currentCard = 0;

  const counter = document.getElementById('carousel-counter');
  const prevBtn = document.getElementById('carousel-prev');
  const nextBtn = document.getElementById('carousel-next');

  function showCard(index) {
    cards[currentCard].classList.remove('active');
    currentCard = (index + total) % total;
    cards[currentCard].classList.add('active');
    if (counter) counter.textContent = `${currentCard + 1} / ${total}`;
    applyScrollLimits(cards[currentCard]);
  }

  // Activate first card
  cards[0].classList.add('active');
  if (counter) counter.textContent = `1 / ${total}`;
  applyScrollLimits(cards[0]);

  if (prevBtn) prevBtn.addEventListener('click', () => showCard(currentCard - 1));
  if (nextBtn) nextBtn.addEventListener('click', () => showCard(currentCard + 1));

  // Keyboard arrows
  document.addEventListener('keydown', (e) => {
    // Only respond if demo2 section is in view
    const section = document.getElementById('demo-predictions');
    if (!section) return;
    const rect = section.getBoundingClientRect();
    const inView = rect.top < window.innerHeight && rect.bottom > 0;
    if (!inView) return;

    if (e.key === 'ArrowLeft') showCard(currentCard - 1);
    if (e.key === 'ArrowRight') showCard(currentCard + 1);
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

init();
