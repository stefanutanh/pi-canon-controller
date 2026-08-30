let isStreaming = false;

function setStatus(text) {
  document.getElementById('status-line').innerText = text.toUpperCase();
}

async function toggleLiveView() {
  const img = document.getElementById('stream');
  const placeholder = document.getElementById('placeholder');
  const hud = document.getElementById('hud');
  const btn = document.getElementById('toggle-stream-btn');

  if (!isStreaming) {
    setStatus('Starting Live View...');
    try {
      const res = await fetch('/api/liveview/start', { method: 'POST' });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to start');
      }
      img.src = '/api/liveview';
      img.style.display = 'block';
      placeholder.style.display = 'none';
      hud.style.display = 'flex';
      btn.classList.add('active');
      btn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
          <rect x="6" y="4" width="4" height="16"></rect>
          <rect x="14" y="4" width="4" height="16"></rect>
        </svg>
        <span>Stoppa Live View</span>
      `;
      isStreaming = true;
      setStatus('Live View Active');
    } catch (err) {
      console.error(err);
      setStatus('Failed to start Live View: ' + err.message.split('\n')[0]);
    }
  } else {
    setStatus('Stopping Live View...');
    try {
      await fetch('/api/liveview/stop', { method: 'POST' });
    } catch (err) {
      console.error(err);
    }
    img.src = '';
    img.style.display = 'none';
    placeholder.style.display = 'flex';
    hud.style.display = 'none';
    btn.classList.remove('active');
    btn.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
      </svg>
      <span>Starta Live View</span>
    `;
    isStreaming = false;
    setStatus('System Ready');
  }
}

async function loadConfig() {
  try {
    setStatus('Syncing Camera Settings...');
    const res = await fetch('/api/config');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const data = await res.json();
    console.log('Hämtad konfiguration:', data);

    ['iso', 'shutterspeed', 'aperture', 'whitebalance', 'imageformat'].forEach(key => {
      const select = document.getElementById(key);
      if (!select || !data[key]) return;

      select.innerHTML = '';
      data[key].choices.forEach(choice => {
        const opt = document.createElement('option');
        opt.value = choice;
        opt.innerText = choice;
        if (choice === data[key].value) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
    });

    setStatus('System Ready');
  } catch (err) {
    console.error('Kunde inte läsa inställningar:', err);
    setStatus('Failed to load settings');
  }
}

async function updateSetting(key, value) {
  setStatus(`Setting ${key} -> ${value}...`);
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value })
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Config Error');
    }
    setStatus('Setting Updated');
  } catch (err) {
    console.error(err);
    setStatus('Config Error: ' + err.message.split('\n')[0]);
  }
}

async function takeStandardPicture() {
  const btn = document.getElementById('capture-btn');
  btn.setAttribute('disabled', 'true');
  setStatus('Exposing...');

  try {
    const res = await fetch('/api/capture', { method: 'POST' });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Capture Failed');
    }
    const data = await res.json();
    if (data.status === 'success') {
      setStatus('Capture Complete');
      showPreview(data.preview_url || data.url, data.filename || data.url.split('/').pop());
      loadGallery();
    } else {
      setStatus('Capture Failed');
    }
  } catch (err) {
    console.error(err);
    setStatus('Error: ' + err.message.split('\n')[0]);
    alert('Capture Error:\n' + err.message);
  } finally {
    btn.removeAttribute('disabled');
  }
}

async function takeBulbPicture() {
  const seconds = parseFloat(document.getElementById('bulb-seconds').value);
  const btn = document.getElementById('bulb-btn');

  if (isStreaming) {
    await toggleLiveView();
  }

  btn.disabled = true;
  let remaining = seconds;
  setStatus(`Bulb Exposing: ${remaining}s`);

  const timer = setInterval(() => {
    remaining -= 1;
    if (remaining > 0) {
      setStatus(`Bulb Exposing: ${remaining}s`);
    } else {
      clearInterval(timer);
      setStatus('Closing Shutter & Transferring...');
    }
  }, 1000);

  try {
    const res = await fetch('/api/bulb', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seconds })
    });
    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Bulb Exposure Failed');
    }
    const data = await res.json();
    clearInterval(timer);

    if (data.status === 'success') {
      setStatus(`Bulb Finished (${seconds}s)`);
      if (data.preview_url || data.url) {
        showPreview(data.preview_url || data.url, data.filename || (data.url ? data.url.split('/').pop() : ''));
      }
      loadGallery();
    } else {
      setStatus('Bulb Exposure Failed');
    }
  } catch (err) {
    clearInterval(timer);
    console.error(err);
    setStatus('Error: ' + err.message.split('\n')[0]);
    alert('Bulb Error:\n' + err.message);
  } finally {
    btn.disabled = false;
  }
}

function showPreview(url, filename) {
  const panel = document.getElementById('preview-panel');
  const img = document.getElementById('latest-image');
  const filenameEl = document.getElementById('preview-filename');

  img.src = url;
  filenameEl.innerText = filename || url.split('/').pop();
  panel.style.display = 'flex';
}

async function loadGallery() {
  try {
    const res = await fetch('/api/captures');
    if (!res.ok) throw new Error("Failed to load gallery");
    const files = await res.json();
    const grid = document.getElementById('gallery-grid');
    if (!grid) return;
    grid.innerHTML = '';

    if (files.length === 0) {
      grid.innerHTML = '<div style="grid-column: span 3; text-align: center; font-size: 0.75rem; color: var(--text-muted); padding: 16px 0;">Inga bilder tagna än</div>';
      return;
    }

    files.forEach(file => {
      const item = document.createElement('a');
      item.href = file.url;
      item.target = '_blank';
      item.className = 'gallery-item';
      item.title = file.filename;

      const img = document.createElement('img');
      img.src = file.preview_url;
      img.loading = 'lazy';

      const label = document.createElement('div');
      label.className = 'gallery-item-info';
      label.innerText = file.filename.split('.').pop().toUpperCase();

      item.appendChild(img);
      item.appendChild(label);
      grid.appendChild(item);
    });
  } catch (err) {
    console.error("Kunde inte ladda galleri:", err);
  }
}

function adjustBulbTime(amount) {
  const input = document.getElementById('bulb-seconds');
  let val = parseFloat(input.value) || 0;
  val = Math.max(1, Math.min(3600, val + amount));
  input.value = val;
}

function setBulbPreset(seconds) {
  const input = document.getElementById('bulb-seconds');
  input.value = seconds;
}

function toggleAdvancedPanel() {
  const panel = document.getElementById('advanced-panel');
  if (panel.style.display === 'none') {
    panel.style.display = 'block';
  } else {
    panel.style.display = 'none';
  }
}

function init() {
  loadConfig();
  loadGallery();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}