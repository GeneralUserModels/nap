const CLUSTER_COLORS = [
  '#819A91', '#A7C1A8', '#8B7355', '#B8860B',
  '#6B8E6B', '#708090', '#9C8B6E', '#5F7A61',
  '#8F9779', '#7A8B7A', '#A08C5B', '#6D7969',
  '#4E7A8B', '#8E6B5F', '#6A8F6E', '#7B6D8E',
  '#5B8A72', '#9B7A5C', '#6E8B9C', '#8B6E7A',
  '#7A9B6E', '#5C6B8A', '#8A7B5E', '#6B9A8B',
  '#9A6B7A', '#4A7A6B', '#8B6B4E', '#6B5A8B',
  '#5E8B6E', '#8B7A6E', '#6E5B7A', '#7A6B5C',
  '#5C8A6B', '#8A5E7A', '#6B8A5C', '#7A5C6B',
  '#5B6E8A', '#8A6B5B', '#6B7A4E', '#7A8A5B'
];
const NOISE_COLOR = '#CCCCCC';
const POINT_RADIUS = 2.5;

let data = null;
let clusterNameMap = {};
let transform = { x: 0, y: 0, scale: 1 };
let canvasW, canvasH;
let dataMinX, dataMaxX, dataMinY, dataMaxY;
let quadtree = null;
let hoveredPoint = null;
let selectedPoint = null;
let isDragging = false;
let didDrag = false;
let dragStart = { x: 0, y: 0 };
let dragTransformStart = { x: 0, y: 0 };

async function init() {
  const canvas = document.getElementById('scatter-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  try {
    const res = await fetch(`${import.meta.env.BASE_URL}data/demo3/embeddings.json`);
    data = await res.json();
  } catch (e) {
    console.error('Demo 3: Failed to load embeddings:', e);
    return;
  }

  if (!data.points?.length) return;

  // Build cluster name lookup
  if (data.clusters) {
    data.clusters.forEach(c => {
      if (c.name) clusterNameMap[c.id] = c.name;
    });
  }

  // Set canvas resolution
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvasW = rect.width;
  canvasH = rect.height;
  canvas.width = canvasW * dpr;
  canvas.height = canvasH * dpr;
  ctx.scale(dpr, dpr);

  // Compute data bounds
  const xs = data.points.map(p => p.x);
  const ys = data.points.map(p => p.y);
  dataMinX = Math.min(...xs);
  dataMaxX = Math.max(...xs);
  dataMinY = Math.min(...ys);
  dataMaxY = Math.max(...ys);

  // Add padding
  const padX = (dataMaxX - dataMinX) * 0.05;
  const padY = (dataMaxY - dataMinY) * 0.05;
  dataMinX -= padX; dataMaxX += padX;
  dataMinY -= padY; dataMaxY += padY;

  // Sync sidebar max-height to canvas height
  const sidebar = document.querySelector('.embeddings-sidebar');
  if (sidebar) sidebar.style.maxHeight = rect.height + 'px';

  // Render legend
  renderLegend(data.clusters || []);

  // Stats
  document.getElementById('stat-points').textContent = data.points.length.toLocaleString();
  document.getElementById('stat-clusters').textContent = (data.clusters || []).filter(c => c.id >= 0).length;

  // Initial draw
  draw(ctx);

  // Mouse events
  canvas.addEventListener('mousemove', (e) => {
    if (isDragging) {
      const dx = e.clientX - dragStart.x;
      const dy = e.clientY - dragStart.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) didDrag = true;
      transform.x = dragTransformStart.x + dx;
      transform.y = dragTransformStart.y + dy;
      draw(ctx);
      return;
    }

    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const nearest = findNearest(mx, my, 15);

    if (nearest !== hoveredPoint) {
      hoveredPoint = nearest;
      draw(ctx);
    }
    canvas.style.cursor = nearest !== null ? 'pointer' : 'crosshair';
  });

  canvas.addEventListener('mousedown', (e) => {
    isDragging = true;
    didDrag = false;
    dragStart = { x: e.clientX, y: e.clientY };
    dragTransformStart = { x: transform.x, y: transform.y };
  });

  window.addEventListener('mouseup', (e) => {
    if (isDragging) {
      isDragging = false;
      canvas.style.cursor = 'crosshair';
    }
  });

  canvas.addEventListener('click', (e) => {
    if (didDrag) return; // ignore click after drag
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const nearest = findNearest(mx, my, 15);

    if (nearest !== null) {
      selectedPoint = nearest;
      showDetailPanel(nearest);
    } else {
      closeDetailPanel();
    }
    draw(ctx);
  });

  canvas.addEventListener('mouseleave', () => {
    hoveredPoint = null;
    draw(ctx);
  });

  // Close panel on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDetailPanel();
  });

  // Close button
  const closeBtn = document.getElementById('detail-close');
  if (closeBtn) {
    closeBtn.addEventListener('click', () => closeDetailPanel());
  }

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    const newScale = Math.max(0.5, Math.min(20, transform.scale * factor));

    // Zoom toward cursor
    transform.x = mx - (mx - transform.x) * (newScale / transform.scale);
    transform.y = my - (my - transform.y) * (newScale / transform.scale);
    transform.scale = newScale;

    draw(ctx);
  }, { passive: false });

  // Touch support
  let lastTouchDist = 0;
  canvas.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) {
      isDragging = true;
      dragStart = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      dragTransformStart = { x: transform.x, y: transform.y };
    } else if (e.touches.length === 2) {
      lastTouchDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
    }
  }, { passive: true });

  canvas.addEventListener('touchmove', (e) => {
    e.preventDefault();
    if (e.touches.length === 1 && isDragging) {
      const dx = e.touches[0].clientX - dragStart.x;
      const dy = e.touches[0].clientY - dragStart.y;
      transform.x = dragTransformStart.x + dx;
      transform.y = dragTransformStart.y + dy;
      draw(ctx);
    } else if (e.touches.length === 2) {
      const dist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const factor = dist / lastTouchDist;
      transform.scale = Math.max(0.5, Math.min(20, transform.scale * factor));
      lastTouchDist = dist;
      draw(ctx);
    }
  }, { passive: false });

  canvas.addEventListener('touchend', () => { isDragging = false; });

  // Resize
  window.addEventListener('resize', () => {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvasW = rect.width;
    canvasH = rect.height;
    canvas.width = canvasW * dpr;
    canvas.height = canvasH * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (sidebar) sidebar.style.maxHeight = rect.height + 'px';
    draw(ctx);
  });
}

function dataToScreen(px, py) {
  const sx = ((px - dataMinX) / (dataMaxX - dataMinX)) * canvasW;
  const sy = ((py - dataMinY) / (dataMaxY - dataMinY)) * canvasH;
  return {
    x: sx * transform.scale + transform.x,
    y: sy * transform.scale + transform.y
  };
}

function screenToData(sx, sy) {
  const nx = (sx - transform.x) / transform.scale;
  const ny = (sy - transform.y) / transform.scale;
  return {
    x: (nx / canvasW) * (dataMaxX - dataMinX) + dataMinX,
    y: (ny / canvasH) * (dataMaxY - dataMinY) + dataMinY
  };
}

function draw(ctx) {
  ctx.clearRect(0, 0, canvasW, canvasH);

  // Background
  ctx.fillStyle = '#FAFAF5';
  ctx.fillRect(0, 0, canvasW, canvasH);

  if (!data) return;

  const points = data.points;
  for (let i = 0; i < points.length; i++) {
    const p = points[i];
    const { x, y } = dataToScreen(p.x, p.y);

    // Skip if off-screen
    if (x < -10 || x > canvasW + 10 || y < -10 || y > canvasH + 10) continue;

    const color = p.cluster >= 0
      ? CLUSTER_COLORS[p.cluster % CLUSTER_COLORS.length]
      : NOISE_COLOR;

    const alpha = 0.75;
    const r = POINT_RADIUS * Math.min(transform.scale, 3);

    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = hexToRgba(color, alpha);
    ctx.fill();
  }

  // Highlight selected point
  if (selectedPoint !== null) {
    const p = points[selectedPoint];
    const { x, y } = dataToScreen(p.x, p.y);
    ctx.beginPath();
    ctx.arc(x, y, POINT_RADIUS * 4, 0, Math.PI * 2);
    ctx.strokeStyle = '#FFFFFF';
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, POINT_RADIUS * 4, 0, Math.PI * 2);
    ctx.strokeStyle = '#2C2C2C';
    ctx.lineWidth = 1.5;
    ctx.stroke();
    ctx.fillStyle = hexToRgba(
      p.cluster >= 0 ? CLUSTER_COLORS[p.cluster % CLUSTER_COLORS.length] : NOISE_COLOR,
      1
    );
    ctx.fill();
  }

  // Highlight hovered (ring only, no tooltip)
  if (hoveredPoint !== null && hoveredPoint !== selectedPoint) {
    const p = points[hoveredPoint];
    const { x, y } = dataToScreen(p.x, p.y);
    ctx.beginPath();
    ctx.arc(x, y, POINT_RADIUS * 3, 0, Math.PI * 2);
    ctx.strokeStyle = '#2C2C2C';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.fillStyle = hexToRgba(
      p.cluster >= 0 ? CLUSTER_COLORS[p.cluster % CLUSTER_COLORS.length] : NOISE_COLOR,
      1
    );
    ctx.fill();
  }
}

function findNearest(mx, my, maxDist) {
  if (!data) return null;
  let best = null;
  let bestDist = maxDist * maxDist;

  for (let i = 0; i < data.points.length; i++) {
    const p = data.points[i];
    const { x, y } = dataToScreen(p.x, p.y);
    const d = (x - mx) ** 2 + (y - my) ** 2;
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  return best;
}

function showDetailPanel(idx) {
  const panel = document.getElementById('detail-panel');
  if (!panel || idx === null) return;

  const p = data.points[idx];
  const clusterName = clusterNameMap[p.cluster] || (p.cluster < 0 ? 'Other' : `Cluster ${p.cluster}`);

  document.getElementById('detail-cluster').textContent = clusterName;

  const hoverText = p.hover || clusterName;
  const body = document.getElementById('detail-body');
  body.textContent = hoverText;

  panel.classList.add('open');
  selectedPoint = idx;
}

function closeDetailPanel() {
  const panel = document.getElementById('detail-panel');
  if (panel) panel.classList.remove('open');
  selectedPoint = null;
}

function renderLegend(clusters) {
  const legend = document.getElementById('embeddings-legend');
  if (!legend) return;

  const sorted = [...clusters].filter(c => c.id >= 0).sort((a, b) => b.count - a.count);

  sorted.forEach(c => {
    const item = document.createElement('div');
    item.className = 'legend-item';
    const color = CLUSTER_COLORS[c.id % CLUSTER_COLORS.length];
    const name = c.name || `Cluster ${c.id}`;
    item.innerHTML = `<span class="legend-dot" style="background:${color}"></span>
      <span>${name} (${c.count})</span>`;
    legend.appendChild(item);
  });

  // Noise
  const noiseCluster = clusters.find(c => c.id === -1);
  if (noiseCluster) {
    const item = document.createElement('div');
    item.className = 'legend-item';
    item.innerHTML = `<span class="legend-dot" style="background:${NOISE_COLOR}"></span>
      <span>Other (${noiseCluster.count})</span>`;
    legend.appendChild(item);
  }
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

init();
