// Scan controls. polling, deployment banner, cancelling scans

function validateGroupInput() {
  var el = document.getElementById('groupId');
  var hint = document.getElementById('groupIdHint');
  var v = el.value.trim();
  if (!v) { hint.textContent = ''; el.classList.remove('input-error'); return false; }
  if (!/^\d+$/.test(v)) { hint.textContent = 'Only numbers allowed'; el.classList.add('input-error'); return false; }
  if (parseInt(v) <= 0) { hint.textContent = 'Must be a positive number'; el.classList.add('input-error'); return false; }
  hint.textContent = ''; el.classList.remove('input-error'); return true;
}

async function startScan() {
  if (!validateGroupInput()) return;
  var groupId = document.getElementById('groupId').value.trim();
  var includeAllies = document.getElementById('includeAllies').checked;
  var includeEnemies = document.getElementById('includeEnemies').checked;
  await _doScan(parseInt(groupId), includeAllies, includeEnemies, document.getElementById('btnScan'), 'Start Custom Scan');
}

async function scanAllSEA() {
  await _doScan(2648601, true, true, document.getElementById('btnScanSEA'), '⚓ Scan all of SEA');
}

async function scanMyDivision() {
  if (!currentUser) return;
  var gid = null, name = 'My Division';
  if (currentUser.division_group_id && currentUser.division_confirmed) {
    gid = currentUser.division_group_id;
    name = currentUser.division_name || 'My Division';
  }
  if (!gid) { alert('No confirmed division found'); return; }
  await _doScan(gid, false, false, document.getElementById('btnScanMyDivision'), '🎖️ Scan ' + name);
}

async function scanMyModeratedDivisions() {
  if (!currentUser) return;
  var divs = currentUser.divisions_mod_confirmed || [];
  if (!divs.length) { alert('No confirmed moderated divisions found'); return; }
  var btn = document.getElementById('btnScanModDivisions');
  var origText = btn.textContent;
  btn.disabled = true; btn.textContent = 'Queuing ' + divs.length + ' scans...';
  var queued = 0;
  for (var i = 0; i < divs.length; i++) {
    var d = divs[i];
    try {
      var resp = await fetch(API_BASE + '/api/scan', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ group_id: d.id, include_allies: false, include_enemies: false })
      });
      var data = await resp.json().catch(function() { return {}; });
      if (resp.ok) {
        queued++;
        _pendingQueueId = data.queue_id;
      } else {
        console.warn('Failed to queue scan for ' + (d.name || d.id) + ': ' + (data.error || 'Unknown error'));
      }
    } catch(e) {
      console.warn('Network error queuing scan for ' + (d.name || d.id));
    }
  }
  btn.disabled = false; btn.textContent = origText;
  if (queued > 0) {
    alert('Queued ' + queued + ' scan(s) for your moderated divisions.');
    document.getElementById('queueStatus').style.display = 'block';
    document.getElementById('queuePosition').textContent = 'Queued ' + queued + ' scan(s)';
    _startQueuePolling();
  } else {
    alert('Failed to queue any scans.');
  }
}

async function _doScan(groupId, includeAllies, includeEnemies, btn, origText) {
  btn.disabled = true; btn.textContent = 'Queuing...';
  try {
    var resp = await fetch(API_BASE + '/api/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ group_id: groupId, include_allies: includeAllies, include_enemies: includeEnemies })
    });
    var data = await resp.json().catch(function() { return {}; });
    if (!resp.ok) {
      alert(data.error || 'Failed to queue scan');
      btn.disabled = false; btn.textContent = origText;
      return;
    }
    _pendingQueueId = data.queue_id;
    btn.disabled = false; btn.textContent = origText;
    if (data.position && data.position > 1) {
      document.getElementById('queueStatus').style.display = 'block';
      document.getElementById('queuePosition').textContent = '#' + data.position;
      _startQueuePolling();
    } else {
      document.getElementById('scanProgress').style.display = 'block';
      document.getElementById('logConsole').innerHTML = '';
      startProgressStream();
    }
  } catch(e) {
    alert('Network error: ' + e.message);
    btn.disabled = false; btn.textContent = origText;
  }
}

// ──────────────────── Queue polling ────────────────────
var _queueTimer = null;
function _startQueuePolling() {
  if (_queueTimer) clearInterval(_queueTimer);
  _queueTimer = setInterval(async function() {
    try {
      var resp = await fetch(API_BASE + '/api/progress');
      var d = await resp.json();
      if (d.status === 'scanning') {
        clearInterval(_queueTimer); _queueTimer = null;
        document.getElementById('queueStatus').style.display = 'none';
        document.getElementById('scanProgress').style.display = 'block';
        document.getElementById('logConsole').innerHTML = '';
        startProgressStream();
        return;
      }
      if (_pendingQueueId) {
        var qResp = await fetch(API_BASE + '/api/queue/' + _pendingQueueId);
        if (qResp.ok) {
          var qData = await qResp.json();
          document.getElementById('queuePosition').textContent = '#' + (qData.position || '?');
          if (qData.status === 'done' || qData.status === 'failed') {
            clearInterval(_queueTimer); _queueTimer = null;
            document.getElementById('queueStatus').style.display = 'none';
            _resetScanButtons();
          }
        }
      }
    } catch(e) {}
  }, 3000);
}

// ──────────────────── Cancel scan ────────────────────
async function cancelScan() {
  if (!confirm('Cancel the running scan?')) return;
  var btn = document.getElementById('btnCancel');
  btn.disabled = true; btn.textContent = 'Cancelling...';
  try {
    var resp = await fetch(API_BASE + '/api/scan/cancel', { method: 'POST' });
    var data = await resp.json().catch(function() { return {}; });
    if (!resp.ok) {
      alert(data.error || 'Failed to cancel scan');
      btn.disabled = false; btn.textContent = '✕ Cancel Scan';
    }
  } catch(e) {
    btn.disabled = false; btn.textContent = '✕ Cancel Scan';
  }
}

function toggleCustomScan() {
  var section = document.getElementById('customScanSection');
  var toggleBtn = document.getElementById('btnCustomToggle');
  if (section.style.display === 'none') { section.style.display = 'block'; toggleBtn.textContent = 'Custom scan ▴'; }
  else { section.style.display = 'none'; toggleBtn.textContent = 'Custom scan ▾'; }
}

// ──────────────────── Progress polling ────────────────────
var _pollTimer = null;
var _logCursor = 0;

function startProgressStream() {
  if (_pollTimer) clearInterval(_pollTimer);
  _logCursor = 0;
  document.getElementById('scanProgress').style.display = 'block';
  var cancelBtn = document.getElementById('btnCancel');
  if (cancelBtn) cancelBtn.style.display = 'inline-flex';

  _pollTimer = setInterval(async function() {
    try {
      var resp = await fetch(API_BASE + '/api/progress?cursor=' + _logCursor);
      var d = await resp.json();

      document.getElementById('progressBar').style.width = d.progress + '%';
      document.getElementById('progressInner').textContent = Math.round(d.progress) + '%';
      if (d.phase) {
        document.getElementById('progressLabel').textContent = d.phase;
        document.getElementById('progressDesc').textContent = d.phase_description || '';
      }
      if (d.eta_seconds != null && d.eta_seconds > 0) {
        document.getElementById('etaBadge').textContent = 'ETA: ' + fmtEta(d.eta_seconds);
        document.getElementById('etaBadge').style.display = 'inline-block';
      } else { document.getElementById('etaBadge').style.display = 'none'; }

      if (d.logs && d.logs.length > 0) {
        var logEl = document.getElementById('logConsole');
        var isNearBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 50;
        var frag = document.createDocumentFragment();
        d.logs.forEach(function(line) {
          var div = document.createElement('div'); div.className = 'log-line'; div.textContent = line; frag.appendChild(div);
        });
        logEl.appendChild(frag);
        if (isNearBottom) logEl.scrollTop = logEl.scrollHeight;
      }

      _logCursor = d.log_count;

      document.getElementById('sPhase').textContent = d.phase || '—';
      document.getElementById('sGroups').textContent = d.groups_done + '/' + d.groups_total;
      document.getElementById('sUsers').textContent = d.users_checked + '/' + d.users_total;
      document.getElementById('sFlagged').textContent = d.flagged_found;
      document.getElementById('sDiscord').textContent = d.discord_ids_found;
      document.getElementById('sEta').textContent = fmtEta(d.eta_seconds);

      var badge = document.getElementById('statusBadge');
      if (d.status === 'scanning') badge.innerHTML = '<span class="pulse" style="color:var(--green)">⬤</span> Scanning...';
      else if (d.status === 'done') badge.innerHTML = '<span style="color:var(--green)">⬤</span> Done';
      else if (d.status === 'error') badge.innerHTML = '<span style="color:var(--red)">⬤</span> Error';
      else if (d.status === 'cancelled') badge.innerHTML = '<span style="color:var(--yellow)">⬤</span> Cancelled';

      if (d.status === 'done' || d.status === 'error' || d.status === 'cancelled') {
        clearInterval(_pollTimer); _pollTimer = null;
        _resetScanButtons();
        if (d.status === 'done' && d.scan_id) loadScanResults(d.scan_id);
        if (d.status === 'error') alert('Scan failed: ' + (d.phase_description || 'Unknown error'));
        if (d.status === 'cancelled') alert('Scan was cancelled.');
      }

      if (cancelBtn) {
        if (d.owned_by_current_user) cancelBtn.style.display = 'inline-flex';
        else cancelBtn.style.display = 'none';
      }
    } catch (e) {}
  }, 1500);
}

function _resetScanButtons() {
  var cBtn = document.getElementById('btnCancel');
  if (cBtn) { cBtn.style.display = 'none'; cBtn.disabled = false; cBtn.textContent = '✕ Cancel Scan'; }
  var btn = document.getElementById('btnScan');
  if (btn) { btn.disabled = false; btn.textContent = 'Start Custom Scan'; }
  var seaBtn = document.getElementById('btnScanSEA');
  if (seaBtn) { seaBtn.disabled = false; seaBtn.textContent = '⚓ Scan all of SEA'; }
  var divBtn = document.getElementById('btnScanMyDivision');
  if (divBtn && currentUser) {
    divBtn.disabled = false;
    divBtn.textContent = '🎖️ Scan ' + (currentUser.division_name || 'My Division');
  }
}

// ──────────────────── Deploy banner polling ────────────────────
var _deployTimer = null;
function startDeployPolling() {
  if (_deployTimer) return;
  _deployTimer = setInterval(async function() {
    try {
      var resp = await fetch(API_BASE + '/api/deploy/status');
      var d = await resp.json();
      var banner = document.getElementById('deployBanner');
      var scanNote = document.getElementById('deployScanNote');
      var msgEl = document.getElementById('deployMessage');
      if (d.pending) {
        if (d.message) msgEl.textContent = d.message;
        banner.style.display = 'flex';
        scanNote.style.display = d.scanning ? 'inline' : 'none';
      } else { banner.style.display = 'none'; }
    } catch (e) { var b = document.getElementById('deployBanner'); if (b) b.style.display = 'none'; }
  }, 5000);
}
