/* ── State ───────────────────────────────────────────────────────────────── */
const state = {
  currentInfo: null,
  downloads: {},          // id → { ...progressFields }
  pollingTimers: {},      // id → intervalId
};

/* ── Link history (localStorage) ─────────────────────────────────────────── */
const HISTORY_KEY = 'videoget_history';
const HISTORY_MAX = 100;

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; }
  catch (_) { return []; }
}

function saveHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items));
}

function addToHistory(url, info) {
  const items = loadHistory().filter(i => i.url !== url); // dedupe
  items.unshift({
    url,
    title: info.title || url,
    platform: info.platform || '',
    thumbnail: info.thumbnail || '',
    addedAt: Date.now(),
  });
  saveHistory(items.slice(0, HISTORY_MAX));
  renderHistory();
}

function deleteFromHistory(url) {
  saveHistory(loadHistory().filter(i => i.url !== url));
  renderHistory();
}

function clearHistory() {
  saveHistory([]);
  renderHistory();
}

function renderHistory() {
  const items = loadHistory();
  const section = $('historySection');
  const list = $('historyList');
  const countEl = $('historyCount');

  if (items.length === 0) {
    hide(section);
    return;
  }

  show(section);
  countEl.textContent = items.length;

  list.innerHTML = items.map(item => {
    const thumbHtml = item.thumbnail
      ? `<img class="history-thumb" src="${escapeHtml(item.thumbnail)}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : `<div class="history-thumb-placeholder" style="background:${platformColor(item.platform, 0.15)};color:${platformColor(item.platform, 1)}">${platformShort(item.platform)}</div>`;

    const displayUrl = item.url.replace(/^https?:\/\//, '').replace(/^www\./, '');

    return `<div class="history-item" onclick="loadFromHistory('${escapeAttr(item.url)}')" title="${escapeHtml(item.url)}">
      ${thumbHtml}
      <div class="history-info">
        <div class="history-title">${escapeHtml(item.title)}</div>
        <div class="history-url">${escapeHtml(truncate(displayUrl, 60))}</div>
      </div>
      <button class="history-delete" onclick="event.stopPropagation();deleteFromHistory('${escapeAttr(item.url)}')" title="Remove">✕</button>
    </div>`;
  }).join('');
}

function loadFromHistory(url) {
  $('urlInput').value = url;
  autoSelectBrowser(url);
  fetchInfo();
}

function platformColor(platform, alpha) {
  const map = {
    youtube: `rgba(255,59,59,${alpha})`,
    x_twitter: `rgba(29,155,240,${alpha})`,
    instagram: `rgba(225,48,108,${alpha})`,
    facebook: `rgba(24,119,242,${alpha})`,
    tiktok: `rgba(254,44,85,${alpha})`,
    bilibili: `rgba(0,161,214,${alpha})`,
    douyin: `rgba(255,66,89,${alpha})`,
    xiaohongshu: `rgba(255,36,66,${alpha})`,
  };
  return map[platform] || `rgba(136,136,136,${alpha})`;
}

function platformShort(platform) {
  return { youtube:'YT', x_twitter:'X', instagram:'IG', facebook:'FB',
           tiktok:'TT', bilibili:'B', douyin:'抖', xiaohongshu:'红' }[platform] || '?';
}

function escapeAttr(str) {
  return String(str).replace(/'/g, '&#39;').replace(/"/g, '&quot;');
}

/* ── DOM helpers ─────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);
const show = el => el.classList.remove('hidden');
const hide = el => el.classList.add('hidden');

/* ── On load ─────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadOutputDir();
  setupQualityButtons();
  renderHistory();

  $('urlInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') fetchInfo();
  });

  // Paste auto-detect: extract URL from any pasted text (e.g. Douyin share text)
  $('urlInput').addEventListener('paste', e => {
    setTimeout(() => {
      const raw = $('urlInput').value;
      const extracted = extractUrl(raw);
      if (extracted && extracted !== raw) {
        $('urlInput').value = extracted;
      }
      if ($('urlInput').value.startsWith('http')) {
        autoSelectBrowser($('urlInput').value);
        fetchInfo();
      }
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
function getSelectedBrowser() {
  return document.getElementById('browserSelect')?.value || '';
}

// Extract the first http/https URL from a block of text
function extractUrl(text) {
  const match = text.match(/https?:\/\/[^\s\u3000-\u9fff，。！？、""''【】（）《》]+/);
  return match ? match[0].replace(/[.,，。！？、]+$/, '') : text.trim();
}

// Auto-suggest browser cookies for platforms that need them
function autoSelectBrowser(url) {
  const sel = document.getElementById('browserSelect');
  if (!sel || sel.value) return; // don't override if user already picked
  const needsCookies = ['youtube.com', 'youtu.be', 'douyin.com', 'v.douyin.com', 'bilibili.com', 'b23.tv',
                        'instagram.com', 'facebook.com', 'fb.watch', 'tiktok.com', 'vm.tiktok.com'];
  if (needsCookies.some(d => url.includes(d))) {
    // Pick Chrome if available, otherwise first real option
    const chrome = sel.querySelector('option[value="chrome"]');
    if (chrome) sel.value = 'chrome';
  }
}

async function fetchInfo() {
  const raw = $('urlInput').value.trim();
  if (!raw) return;

  // Auto-extract URL from share text (e.g. Douyin/WeChat share snippets)
  const url = extractUrl(raw);
  if (url !== raw) $('urlInput').value = url;

  autoSelectBrowser(url);
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
      body: JSON.stringify({ url, cookies_from_browser: getSelectedBrowser() }),
    });
    const data = await res.json();

    if (data.error) {
      showError(data.error);
    } else {
      renderInfo(data);
      addToHistory(url, data);
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
      body: JSON.stringify({ url, quality, cookies_from_browser: getSelectedBrowser() }),
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
           facebook: 'Facebook', tiktok: 'TikTok',
           bilibili: 'Bilibili', douyin: 'Douyin 抖音', xiaohongshu: '小红书 RED' }[p] || p;
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
