let manifest = [];
let currentSegment = 0;
let video = null;
let lastLabelIndex = -1;

async function init() {
  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/demo1/manifest.json`);
    manifest = await res.json();
  } catch (e) {
    console.error('Failed to load Demo 1 manifest:', e);
    return;
  }

  if (!manifest.length) return;

  video = document.getElementById('napsack-video');
  if (!video) return;

  // Build segment tabs
  const segContainer = document.getElementById('napsack-segments');
  manifest.forEach((seg, i) => {
    const btn = document.createElement('button');
    btn.textContent = seg.title;
    if (i === 0) btn.classList.add('active');
    btn.addEventListener('click', () => switchSegment(i));
    segContainer.appendChild(btn);
  });

  // Video time update -> sync labels
  video.addEventListener('timeupdate', () => {
    syncLabel(video.currentTime);
    updateProgress();
  });

  // Sync stack height once video dimensions are known
  video.addEventListener('loadedmetadata', syncStackHeight);

  // Play/pause button
  const playBtn = document.getElementById('napsack-playpause');
  playBtn.addEventListener('click', togglePlayPause);

  // Progress bar seeking
  const progressWrap = document.getElementById('napsack-progress-wrap');
  progressWrap.addEventListener('click', (e) => {
    const rect = progressWrap.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    if (video.duration) {
      video.currentTime = ratio * video.duration;
    }
  });

  // Update play/pause icon on state changes
  video.addEventListener('play', updatePlayIcon);
  video.addEventListener('pause', updatePlayIcon);

  // Auto-advance to next segment when video ends
  video.addEventListener('ended', () => {
    if (currentSegment < manifest.length - 1) {
      switchSegment(currentSegment + 1);
    }
  });

  // Load first segment
  loadSegment(0);
}

function loadSegment(index) {
  const seg = manifest[index];
  video.src = import.meta.env.BASE_URL + seg.video.replace(/^\//, '');
  video.load();

  // Slow playback: encoded at 1fps, play at 0.5x → 2 seconds per frame
  video.playbackRate = 0.5;

  // Match stack height to video viewport
  const viewport = document.querySelector('.napsack-viewport');
  const stack = document.getElementById('napsack-label-stack');
  if (viewport) {
    stack.style.maxHeight = viewport.offsetHeight + 'px';
  }

  // Clear stack and reset label tracking
  stack.innerHTML = '';
  lastLabelIndex = -1;

  // Add first label card immediately with active highlight
  if (seg.labels && seg.labels.length > 0) {
    createLabelCard(stack, seg.labels[0], true);
    lastLabelIndex = 0;
  }

  // Reset progress
  document.getElementById('napsack-progress-bar').style.width = '0%';

  // Auto-play
  video.play().catch(() => {
    // Autoplay might be blocked, that's ok
  });
}

function switchSegment(index) {
  currentSegment = index;

  // Update tab active state
  const tabs = document.querySelectorAll('#napsack-segments button');
  tabs.forEach((t, i) => t.classList.toggle('active', i === index));

  loadSegment(index);
}

function syncLabel(currentTime) {
  const seg = manifest[currentSegment];
  if (!seg || !seg.labels) return;

  // Find the index of the active label whose time is <= currentTime
  let labelIndex = -1;
  for (let i = 0; i < seg.labels.length; i++) {
    if (seg.labels[i].time <= currentTime) {
      labelIndex = i;
    } else {
      break;
    }
  }

  const stack = document.getElementById('napsack-label-stack');

  if (labelIndex < lastLabelIndex) {
    // Seeked backward — remove cards that are in the future
    const cards = stack.querySelectorAll('.napsack-label-card');
    cards.forEach((card, i) => {
      // Cards are prepended, so index 0 = newest (lastLabelIndex), last = oldest (0)
      const cardLabelIndex = lastLabelIndex - i;
      if (cardLabelIndex > labelIndex) {
        card.remove();
      }
    });
    // Mark the new top card as active
    const topCard = stack.firstElementChild;
    if (topCard) topCard.classList.add('active');
    lastLabelIndex = labelIndex;
  } else if (labelIndex > lastLabelIndex) {
    // Remove active class from current green card
    const prev = stack.querySelector('.napsack-label-card.active');
    if (prev) prev.classList.remove('active');

    // Add new cards; only the last one (newest) gets active
    for (let i = lastLabelIndex + 1; i <= labelIndex; i++) {
      createLabelCard(stack, seg.labels[i], i === labelIndex);
    }

    // Keep stack scrolled to top so newest card is visible
    stack.scrollTop = 0;

    lastLabelIndex = labelIndex;
  }
}

function createLabelCard(stack, label, isActive) {
  const card = document.createElement('div');
  card.className = 'napsack-label-card' + (isActive ? ' active' : '');

  const text = document.createElement('p');
  text.className = 'napsack-label-text';
  text.textContent = label.text;

  const time = document.createElement('span');
  time.className = 'napsack-label-time';
  time.textContent = label.timestamp || '';

  card.appendChild(text);
  card.appendChild(time);

  // Insert hidden to measure height, then animate in
  card.style.opacity = '0';
  card.style.transform = 'translateY(-20px)';
  card.style.transition = 'none';
  stack.prepend(card);

  // Measure actual height including gap, then collapse with negative margin
  const height = card.offsetHeight;
  const gap = parseFloat(getComputedStyle(stack).gap) || 0;
  card.style.marginTop = -(height + gap) + 'px';

  // Force reflow, then animate everything in
  card.getBoundingClientRect();
  card.style.transition = '';
  requestAnimationFrame(() => {
    card.style.opacity = '1';
    card.style.transform = 'translateY(0)';
    card.style.marginTop = '0';
  });
}

function syncStackHeight() {
  const viewport = document.querySelector('.napsack-viewport');
  const stack = document.getElementById('napsack-label-stack');
  if (viewport && stack) {
    stack.style.maxHeight = viewport.offsetHeight + 'px';
  }
}

function updateProgress() {
  if (!video || !video.duration) return;
  const pct = (video.currentTime / video.duration) * 100;
  document.getElementById('napsack-progress-bar').style.width = pct + '%';
}

function togglePlayPause() {
  if (!video) return;
  if (video.paused) {
    video.play();
  } else {
    video.pause();
  }
}

function updatePlayIcon() {
  const playIcon = document.querySelector('.icon-play');
  const pauseIcon = document.querySelector('.icon-pause');
  if (!playIcon || !pauseIcon) return;

  if (video.paused) {
    playIcon.style.display = '';
    pauseIcon.style.display = 'none';
  } else {
    playIcon.style.display = 'none';
    pauseIcon.style.display = '';
  }
}

init();
