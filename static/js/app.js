/* ── State ───────────────────────────────────────────────────────────────── */
const state = {
  currentInfo: null,
  downloads: {},          // id → { ...progressFields }
  pollingTimers: {},      // id → intervalId
};

/* ── DOM helpers ─────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const show = el => el.classList.remove('hidden');
const hide = el => el.classList.add('hidden');

/* ── On load ─────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadOutputDir();
  setupQualityButtons();

  $('urlInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') fetchInfo();
  });

  // Paste auto-detect: if the input already has a URL, kick off a fetch
  $('urlInput').addEventListener('paste', () => {
    setTimeout(() => {
      if ($('urlInput').value.startsWith('http')) fetchInfo();
    }, 50);
  });
});

async function loadOutputDir() {
  try {
    const r = await fetch('/api/output_dir');
    const d = await r.json();
    $('outputDirText').textContent = d.path;
  } catch (_) {}
}

/* ── Quality buttons ─────────────────────────────────────────────────────── */
function setupQualityButtons() {
  document.querySelectorAll('.quality-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.quality-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      btn.querySelector('input').checked = true;
    });
  });
}

function getSelectedQuality() {
  const checked = document.querySelector('input[name="quality"]:checked');
  return checked ? checked.value : 'best';
}

/* ── Fetch video info ─────────────────────────────────────────────────────── */
async function fetchInfo() {
  const url = $('urlInput').value.trim();
  if (!url) return;

  clearError();
  hide($('infoCard'));

  const btn = $('fetchBtn');
  btn.disabled = true;
  btn.querySelector('.btn-text').classList.add('hidden');
  btn.querySelector('.btn-spinner').classList.remove('hidden');

  try {
    const res = await fetch('/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (data.error) {
      showError(data.error);
    } else {
      renderInfo(data);
    }
  } catch (err) {
    showError('Could not reach the server. Is it running?');
  } finally {
    btn.disabled = false;
    btn.querySelector('.btn-text').classList.remove('hidden');
    btn.querySelector('.btn-spinner').classList.add('hidden');
  }
}

function renderInfo(info) {
  state.currentInfo = info;

  // Thumbnail
  const thumb = $('infoThumb');
  if (info.thumbnail) {
    thumb.src = info.thumbnail;
    thumb.style.display = 'block';
  } else {
    thumb.style.display = 'none';
  }

  // Duration
  const dur = $('infoDuration');
  if (info.duration) {
    dur.textContent = formatDuration(info.duration);
    show(dur);
  } else {
    hide(dur);
  }

  // Platform badge
  const badge = $('infoPlatformBadge');
  const platform = info.platform || 'unknown';
  badge.className = `platform-badge ${platform}`;
  badge.textContent = platformLabel(platform);

  // Title, uploader
  $('infoTitle').textContent = info.title || 'Unknown title';
  $('infoUploader').textContent = info.uploader || '';

  // Stats
  const views = $('infoViews');
  const likes = $('infoLikes');
  if (info.view_count != null) {
    views.textContent = `👁 ${formatCount(info.view_count)} views`;
    show(views);
  } else { hide(views); }
  if (info.like_count != null) {
    likes.textContent = `♥ ${formatCount(info.like_count)}`;
    show(likes);
  } else { hide(likes); }

  show($('infoCard'));
}

/* ── Start download ──────────────────────────────────────────────────────── */
async function startDownload() {
  const url = $('urlInput').value.trim();
  if (!url) return;

  clearError();
  const quality = getSelectedQuality();

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, quality }),
    });
    const data = await res.json();

    if (data.error) {
      showError(data.error);
      return;
    }

    const id = data.download_id;
    const title = state.currentInfo?.title || url;

    state.downloads[id] = {
      id,
      title,
      status: 'starting',
      percent: 0,
      speed: '',
      eta: '',
      filename: '',
      error: null,
    };

    show($('downloadsSection'));
    renderDownloads();
    startPolling(id);
  } catch (err) {
    showError('Download request failed. Is the server running?');
  }
}

/* ── Polling ─────────────────────────────────────────────────────────────── */
function startPolling(id) {
  if (state.pollingTimers[id]) return;

  const timer = setInterval(async () => {
    try {
      const res = await fetch(`/api/progress/${id}`);
      const data = await res.json();
      if (data.error) {
        clearInterval(timer);
        delete state.pollingTimers[id];
        return;
      }

      state.downloads[id] = { ...state.downloads[id], ...data, id };
      renderDownloads();

      if (data.status === 'done' || data.status === 'error') {
        clearInterval(timer);
        delete state.pollingTimers[id];
      }
    } catch (_) {}
  }, 800);

  state.pollingTimers[id] = timer;
}

/* ── Render download items ───────────────────────────────────────────────── */
function renderDownloads() {
  const list = $('downloadsList');
  const ids = Object.keys(state.downloads).reverse();

  list.innerHTML = ids.map(id => {
    const d = state.downloads[id];
    const isActive = d.status === 'downloading' || d.status === 'starting' || d.status === 'processing';
    const statusClass = d.status;

    const itemClass = d.status === 'done' ? 'done' : d.status === 'error' ? 'error' : 'active';
    const label = d.filename || d.title || id;

    const pct = d.percent ?? 0;
    const barWidth = d.status === 'done' ? 100 : pct;

    const metaHtml = isActive
      ? `<span>${d.speed || '–'}</span><span>ETA ${d.eta || '–'}</span><span>${pct.toFixed(1)}%</span>`
      : d.status === 'done'
      ? `<span style="color:var(--success)">✓ Saved to downloads folder</span>`
      : '';

    const errHtml = d.error
      ? `<div class="dl-error">⚠ ${escapeHtml(d.error)}</div>`
      : '';

    return `
      <div class="dl-item ${itemClass}">
        <div class="dl-header">
          <span class="dl-filename" title="${escapeHtml(label)}">${escapeHtml(truncate(label, 60))}</span>
          <span class="dl-status ${statusClass}">${statusLabel(d.status)}</span>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar" style="width:${barWidth}%"></div>
        </div>
        <div class="dl-meta">${metaHtml}</div>
        ${errHtml}
      </div>
    `;
  }).join('');
}

/* ── Error handling ──────────────────────────────────────────────────────── */
function showError(msg) {
  $('errorText').textContent = msg;
  show($('errorBanner'));
}
function clearError() { hide($('errorBanner')); }

/* ── Formatters ──────────────────────────────────────────────────────────── */
function formatDuration(secs) {
  if (!secs) return '';
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

function formatCount(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(n);
}

function platformLabel(p) {
  return { youtube: 'YouTube', x_twitter: 'X / Twitter', instagram: 'Instagram',
           facebook: 'Facebook', tiktok: 'TikTok' }[p] || p;
}

function statusLabel(s) {
  return { starting: 'Starting…', downloading: 'Downloading', processing: 'Processing',
           done: 'Done', error: 'Error' }[s] || s;
}

function truncate(str, n) {
  return str.length > n ? str.slice(0, n) + '…' : str;
}

function escapeHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
