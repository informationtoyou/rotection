const API_BASE = '';
let currentScanData = null;
let allUsers = [];
let filteredUsers = [];
let sortCol = 'name';
let sortDir = 1;
let currentPage = 1;
let perPage = 100;
let discordFormat = 'space';
let groupChartInstance = null;
let flagChartInstance = null;
let confChartInstance = null;

const FLAG_MAP = {
  0:{name:'Unflagged',color:'#6b7280'}, 1:{name:'Flagged',color:'#ef4444'},
  2:{name:'Confirmed',color:'#dc2626'}, 3:{name:'Queued',color:'#f59e0b'},
  5:{name:'Mixed',color:'#f97316'}, 6:{name:'Past Offender',color:'#8b5cf6'}
};

const SAFE_THUMB_PREFIX = 'https://tr.rbxcdn.com/';

// -- sanitize thumbnail URLs to prevent XSS --
function safeThumbnail(url) {
  if (!url) return '';
  return url.startsWith(SAFE_THUMB_PREFIX) ? esc(url) : '';
}

// -- sanitize discord IDs (digits only) --
function safeDiscordId(id) {
  return /^\d+$/.test(id) ? id : esc(id);
}

// -- tabs --
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'history') loadHistory();
  });
});

// -- input validation --
function validateGroupInput() {
  const el = document.getElementById('groupId');
  const hint = document.getElementById('groupIdHint');
  const v = el.value.trim();
  if (!v) { hint.textContent = ''; el.classList.remove('input-error'); return false; }
  if (!/^\d+$/.test(v)) {
    hint.textContent = 'Only numbers allowed';
    el.classList.add('input-error');
    return false;
  }
  if (parseInt(v) <= 0) {
    hint.textContent = 'Must be a positive number';
    el.classList.add('input-error');
    return false;
  }
  hint.textContent = '';
  el.classList.remove('input-error');
  return true;
}

// -- start scan --
async function startScan() {
  if (!validateGroupInput()) return;
  const groupId = document.getElementById('groupId').value.trim();
  const includeAllies = document.getElementById('includeAllies').checked;
  const includeEnemies = document.getElementById('includeEnemies').checked;
  const btn = document.getElementById('btnScan');
  btn.disabled = true; btn.textContent = 'Starting...';

  try {
    const resp = await fetch(API_BASE + '/api/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ group_id: parseInt(groupId), include_allies: includeAllies, include_enemies: includeEnemies })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      alert(data.error || 'Failed to start scan');
      btn.disabled = false; btn.textContent = 'Start Custom Scan';
      return;
    }
    document.getElementById('scanProgress').style.display = 'block';
    document.getElementById('logConsole').innerHTML = '';
    startProgressStream();
  } catch(e) {
    alert('Network error: ' + e.message);
    btn.disabled = false; btn.textContent = 'Start Custom Scan';
  }
}

// -- scan all of SEA --
async function scanAllSEA() {
  const btn = document.getElementById('btnScanSEA');
  btn.disabled = true; btn.textContent = 'Starting...';

  try {
    const resp = await fetch(API_BASE + '/api/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ group_id: 2648601, include_allies: true, include_enemies: true })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      alert(data.error || 'Failed to start scan');
      btn.disabled = false; btn.textContent = '⚓ Scan all of SEA';
      return;
    }
    document.getElementById('scanProgress').style.display = 'block';
    document.getElementById('logConsole').innerHTML = '';
    startProgressStream();
  } catch(e) {
    alert('Network error: ' + e.message);
    btn.disabled = false; btn.textContent = '⚓ Scan all of SEA';
  }
}

// -- cancel scan --
async function cancelScan() {
  if (!confirm('Cancel the running scan?')) return;
  const btn = document.getElementById('btnCancel');
  btn.disabled = true; btn.textContent = 'Cancelling...';
  try {
    await fetch(API_BASE + '/api/scan/cancel', { method: 'POST' });
  } catch(e) {}
}

// -- toggle custom scan section --
function toggleCustomScan() {
  const section = document.getElementById('customScanSection');
  const toggleBtn = document.getElementById('btnCustomToggle');
  if (section.style.display === 'none') {
    section.style.display = 'block';
    toggleBtn.textContent = 'Custom scan ▴';
  } else {
    section.style.display = 'none';
    toggleBtn.textContent = 'Custom scan ▾';
  }
}

// -- ETA formatter --
function fmtEta(seconds) {
  if (seconds == null || seconds <= 0) return '—';
  if (seconds < 60) return Math.round(seconds) + 's';
  if (seconds < 3600) return Math.round(seconds / 60) + 'm ' + Math.round(seconds % 60) + 's';
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h + 'h ' + m + 'm';
}

// -- polling progress --
let _pollTimer = null;
let _logCursor = 0;

function startProgressStream() {
  if (_pollTimer) clearInterval(_pollTimer);
  _logCursor = 0;
  document.getElementById('scanProgress').style.display = 'block';
  const cancelBtn = document.getElementById('btnCancel');
  if (cancelBtn) cancelBtn.style.display = 'inline-flex';

  _pollTimer = setInterval(async () => {
    try {
      const resp = await fetch(API_BASE + '/api/progress?cursor=' + _logCursor);
      const d = await resp.json();

      document.getElementById('progressBar').style.width = d.progress + '%';
      document.getElementById('progressInner').textContent = Math.round(d.progress) + '%';
      if (d.phase) {
        document.getElementById('progressLabel').textContent = d.phase;
        document.getElementById('progressDesc').textContent = d.phase_description || '';
      }
      if (d.eta_seconds != null && d.eta_seconds > 0) {
        const etaStr = fmtEta(d.eta_seconds);
        document.getElementById('etaBadge').textContent = 'ETA: ' + etaStr;
        document.getElementById('etaBadge').style.display = 'inline-block';
      } else {
        document.getElementById('etaBadge').style.display = 'none';
      }

      if (d.logs && d.logs.length > 0) {
        const logEl = document.getElementById('logConsole');
        const frag = document.createDocumentFragment();
        d.logs.forEach(line => {
          const div = document.createElement('div');
          div.className = 'log-line';
          div.textContent = line;
          frag.appendChild(div);
        });
        logEl.appendChild(frag);
        logEl.scrollTop = logEl.scrollHeight;
      }
      _logCursor = d.log_count;

      document.getElementById('sPhase').textContent = d.phase || '—';
      document.getElementById('sGroups').textContent = d.groups_done + '/' + d.groups_total;
      document.getElementById('sUsers').textContent = d.users_checked + '/' + d.users_total;
      document.getElementById('sFlagged').textContent = d.flagged_found;
      document.getElementById('sDiscord').textContent = d.discord_ids_found;
      document.getElementById('sEta').textContent = fmtEta(d.eta_seconds);

      const badge = document.getElementById('statusBadge');
      if (d.status === 'scanning') badge.innerHTML = '<span class="pulse" style="color:var(--green)">⬤</span> Scanning...';
      else if (d.status === 'done') badge.innerHTML = '<span style="color:var(--green)">⬤</span> Done';
      else if (d.status === 'error') badge.innerHTML = '<span style="color:var(--red)">⬤</span> Error';
      else if (d.status === 'cancelled') badge.innerHTML = '<span style="color:var(--yellow)">⬤</span> Cancelled';

      if (d.status === 'done' || d.status === 'error' || d.status === 'cancelled') {
        clearInterval(_pollTimer);
        _pollTimer = null;
        var cBtn = document.getElementById('btnCancel');
        if (cBtn) { cBtn.style.display = 'none'; cBtn.disabled = false; cBtn.textContent = '✕ Cancel Scan'; }
        var btn = document.getElementById('btnScan');
        if (btn) { btn.disabled = false; btn.textContent = 'Start Custom Scan'; }
        var seaBtn = document.getElementById('btnScanSEA');
        if (seaBtn) { seaBtn.disabled = false; seaBtn.textContent = '⚓ Scan all of SEA'; }
        if (d.status === 'done' && d.scan_id) loadScanResults(d.scan_id);
        if (d.status === 'error') {
          alert('Scan failed: ' + (d.phase_description || 'Unknown error'));
        }
        if (d.status === 'cancelled') {
          alert('Scan was cancelled.');
        }
      }
    } catch (e) {
      // network blip — keep polling
    }
  }, 1500);
}

// -- load scan results --
async function loadScanResults(scanId) {
  document.getElementById('resultsContent').innerHTML =
    '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading scan results...</p></div>';
  document.getElementById('statsContent').innerHTML =
    '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading statistics...</p></div>';
  try {
    const resp = await fetch(API_BASE + '/api/scans/' + scanId);
    if (!resp.ok) return;
    currentScanData = await resp.json();
    renderResults();
    renderStats();
    renderDiscordPanel();
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    document.querySelector('[data-tab="results"]').classList.add('active');
    document.getElementById('panel-results').classList.add('active');
  } catch(e) { console.error(e); }
}

// -- render results --
function renderResults() {
  if (!currentScanData) return;
  const d = currentScanData;
  allUsers = Object.values(d.users || {});
  currentPage = 1;

  const groupSet = new Map();
  const flagSet = new Set();
  allUsers.forEach(u => {
    const gn = u.group_name || 'Unknown';
    groupSet.set(gn, (groupSet.get(gn) || 0) + 1);
    flagSet.add(u.flagType !== undefined ? u.flagType : -1);
  });
  const groups = [...groupSet.entries()].sort((a,b) => b[1] - a[1]);

  var html = '';

  html += '<div class="stats">';
  html += '<div class="stat"><div class="stat-value">' + (d.total_flagged||0) + '</div><div class="stat-label">Flagged Users</div></div>';
  html += '<div class="stat"><div class="stat-value">' + (d.total_discord_ids||0) + '</div><div class="stat-label">Discord IDs</div></div>';
  html += '<div class="stat"><div class="stat-value">' + Object.keys(d.groups||{}).length + '</div><div class="stat-label">Groups Scanned</div></div>';
  html += '<div class="stat"><div class="stat-value small">' + esc(d.primary_group_name||'?') + '</div><div class="stat-label">Primary Group</div></div>';
  var ts = d.timestamp ? new Date(d.timestamp).toLocaleString() : '?';
  html += '<div class="stat"><div class="stat-value small">' + ts + '</div><div class="stat-label">Scan Time</div></div>';
  html += '</div>';

  html += '<div class="card"><h2>Group Filter</h2>';
  html += '<div class="group-nav">';
  html += '<div class="group-chip active" data-group="" onclick="filterByGroup(this)">All Groups <span class="count">' + allUsers.length + '</span></div>';
  var primaryGroupName = d.primary_group_name || '';
  for (var gi2 = 0; gi2 < groups.length; gi2++) {
    var gn = groups[gi2][0], cnt = groups[gi2][1];
    var isPrimary = gn === primaryGroupName;
    html += '<div class="group-chip' + (isPrimary ? ' primary' : '') + '" data-group="' + esc(gn) + '" onclick="filterByGroup(this)">' + esc(gn) + ' <span class="count">' + cnt + '</span></div>';
  }
  html += '</div></div>';

  html += '<div class="card"><h2>Filters</h2>';
  html += '<div class="filter-bar">';
  html += '<input type="text" class="search-input" id="searchInput" placeholder="Search username, display name, or ID..." oninput="applyFilters()">';
  html += '<select id="filterFlag" onchange="applyFilters()"><option value="">All Flags</option>';
  Object.entries(FLAG_MAP).forEach(function(entry) {
    var k = entry[0], v = entry[1];
    if (flagSet.has(parseInt(k))) html += '<option value="' + k + '">' + v.name + '</option>';
  });
  html += '</select>';
  html += '<div class="range-group"><label class="filter-label">Min conf:</label>';
  html += '<input type="range" id="filterConfMin" min="0" max="100" value="0" oninput="applyFilters();document.getElementById(\'confMinVal\').textContent=this.value+\'%\'">';
  html += '<span id="confMinVal" class="filter-label" style="min-width:30px">0%</span></div>';
  html += '<label class="filter-check-label"><input type="checkbox" id="filterActionable" onchange="applyFilters()" class="accent-check"> Actionable only</label>';
  html += '<label class="filter-check-label"><input type="checkbox" id="filterHasDiscord" onchange="applyFilters()" class="accent-check"> Has Discord</label>';
  html += '</div>';
  html += '<div class="filter-summary" id="filterSummary"></div>';
  html += '</div>';

  html += '<div class="card"><h2>Users <span id="resultCount" class="result-count"></span></h2>';
  html += '<div class="pagination" id="paginationTop"></div>';
  html += '<div class="tbl-wrap"><table><thead><tr>';
  html += '<th onclick="doSort(\'name\')" id="th-name">User</th>';
  html += '<th onclick="doSort(\'flagType\')" id="th-flagType">Flag</th>';
  html += '<th onclick="doSort(\'confidence\')" id="th-confidence">Confidence</th>';
  html += '<th onclick="doSort(\'group_name\')" id="th-group_name">Group</th>';
  html += '<th>Reasons</th><th>Discord</th>';
  html += '<th onclick="doSort(\'isActive\')" id="th-isActive">Active</th>';
  html += '<th>Details</th>';
  html += '</tr></thead><tbody id="resultsBody"></tbody></table></div>';
  html += '<div class="pagination" id="paginationBottom"></div>';
  html += '</div>';

  document.getElementById('resultsContent').innerHTML = html;
  applyFilters();
}

function filterByGroup(el) {
  document.querySelectorAll('.group-chip').forEach(c => c.classList.remove('active'));
  el.classList.add('active');
  applyFilters();
}

function applyFilters() {
  if (!allUsers.length) return;
  var search = (document.getElementById('searchInput') ? document.getElementById('searchInput').value : '').toLowerCase();
  var activeChip = document.querySelector('.group-chip.active');
  var activeGroup = activeChip ? (activeChip.dataset.group || '') : '';
  var flag = document.getElementById('filterFlag') ? document.getElementById('filterFlag').value : '';
  var confMin = parseInt(document.getElementById('filterConfMin') ? document.getElementById('filterConfMin').value : '0');
  var actionable = document.getElementById('filterActionable') ? document.getElementById('filterActionable').checked : false;
  var hasDiscord = document.getElementById('filterHasDiscord') ? document.getElementById('filterHasDiscord').checked : false;

  filteredUsers = allUsers.filter(function(u) {
    if (search && !(u.name||'').toLowerCase().includes(search) && !String(u.id).includes(search) && !(u.displayName||'').toLowerCase().includes(search)) return false;
    if (activeGroup && u.group_name !== activeGroup) return false;
    if (flag !== '' && u.flagType !== parseInt(flag)) return false;
    var conf = u.confidence ? Math.round(u.confidence * 100) : 0;
    if (conf < confMin) return false;
    if (actionable && !u.actionable) return false;
    if (hasDiscord && (!u.discord_accounts || u.discord_accounts.length === 0)) return false;
    return true;
  });

  filteredUsers.sort(function(a, b) {
    var va = a[sortCol] != null ? a[sortCol] : '';
    var vb = b[sortCol] != null ? b[sortCol] : '';
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    return va < vb ? -1 * sortDir : va > vb ? 1 * sortDir : 0;
  });

  document.querySelectorAll('th').forEach(th => th.classList.remove('sorted'));
  var sortTh = document.getElementById('th-' + sortCol);
  if (sortTh) sortTh.classList.add('sorted');

  currentPage = 1;
  renderPage();
}

function doSort(col) {
  if (sortCol === col) sortDir *= -1;
  else { sortCol = col; sortDir = 1; }
  applyFilters();
}

function renderPage() {
  var total = filteredUsers.length;
  var totalPages = Math.max(1, Math.ceil(total / perPage));
  if (currentPage > totalPages) currentPage = totalPages;
  var start = (currentPage - 1) * perPage;
  var end = Math.min(start + perPage, total);
  var page = filteredUsers.slice(start, end);

  document.getElementById('resultCount').textContent = 'Showing ' + (start+1) + '–' + end + ' of ' + total + ' (' + allUsers.length + ' total)';
  document.getElementById('filterSummary').textContent =
    total === allUsers.length ? '' : total + ' users match your filters out of ' + allUsers.length + ' total';

  var pagHtml = buildPagination(totalPages);
  document.getElementById('paginationTop').innerHTML = pagHtml;
  document.getElementById('paginationBottom').innerHTML = pagHtml;

  var body = document.getElementById('resultsBody');
  var html = '';
  page.forEach(function(u) {
    var ft = FLAG_MAP[u.flagType] || {name:'Unknown',color:'#6b7280'};
    var conf = u.confidence ? Math.round(u.confidence * 100) : 0;
    var confColor = conf >= 80 ? 'var(--red)' : conf >= 50 ? 'var(--orange)' : 'var(--yellow)';
    var thumb = safeThumbnail(u.thumbnailUrl);
    var discords = (u.discord_accounts || []).slice(0,3).map(function(d) { return '<span class="discord-id">' + safeDiscordId(d.id) + '</span>'; }).join(' ');
    var moreDiscords = (u.discord_accounts || []).length > 3 ? '<span class="text-muted text-xs">+' + (u.discord_accounts.length-3) + '</span>' : '';
    var reasonCount = (u.reasons || []).length;

    html += '<tr>';
    html += '<td>' + (thumb ? '<img class="avatar" src="' + thumb + '" loading="lazy" onerror="this.style.display=\'none\'">' : '') + '<strong>' + esc(u.name) + '</strong><br><span class="text-muted text-xs">' + esc(u.displayName||'') + ' · ' + u.id + '</span></td>';
    html += '<td><span class="flag-badge" style="background:' + ft.color + '">' + ft.name + '</span></td>';
    html += '<td><div class="confidence-bar"><div class="confidence-fill" style="width:' + conf + '%;background:' + confColor + '"></div></div>' + conf + '%</td>';
    html += '<td class="text-xs">' + esc(u.group_name||'?') + '</td>';
    html += '<td class="text-xs">' + (reasonCount > 0 ? '<span class="text-danger">' + reasonCount + ' reason' + (reasonCount>1?'s':'') + '</span>' : '—') + '</td>';
    html += '<td>' + discords + (moreDiscords || (!discords ? '<span class="text-muted text-xs">None</span>' : '')) + '</td>';
    html += '<td><span class="status-dot ' + (u.isActive?'active':'inactive') + '"></span>' + (u.isActive?'Yes':'No') + '</td>';
    html += '<td><button class="btn btn-secondary btn-sm" onclick="showUserDetail(' + u.id + ')">View</button></td>';
    html += '</tr>';
  });
  body.innerHTML = html;
}

function buildPagination(totalPages) {
  if (totalPages <= 1) return '';
  var h = '<div class="info">Page ' + currentPage + ' of ' + totalPages + '</div>';
  h += '<div class="pagination-controls">';
  h += '<select class="per-page-select" onchange="perPage=parseInt(this.value);currentPage=1;renderPage()">';
  [50,100,250,500].forEach(function(n) { h += '<option value="' + n + '" ' + (perPage===n?'selected':'') + '>' + n + ' per page</option>'; });
  h += '</select>';
  h += '<div class="page-btns">';
  h += '<button onclick="goPage(1)" ' + (currentPage===1?'disabled':'') + '>«</button>';
  h += '<button onclick="goPage(' + (currentPage-1) + ')" ' + (currentPage===1?'disabled':'') + '>‹</button>';
  var range = 2;
  var startP = Math.max(1, currentPage - range);
  var endP = Math.min(totalPages, currentPage + range);
  if (startP > 1) h += '<button disabled>…</button>';
  for (var i = startP; i <= endP; i++) {
    h += '<button onclick="goPage(' + i + ')" class="' + (i===currentPage?'active':'') + '">' + i + '</button>';
  }
  if (endP < totalPages) h += '<button disabled>…</button>';
  h += '<button onclick="goPage(' + (currentPage+1) + ')" ' + (currentPage===totalPages?'disabled':'') + '>›</button>';
  h += '<button onclick="goPage(' + totalPages + ')" ' + (currentPage===totalPages?'disabled':'') + '>»</button>';
  h += '</div></div>';
  return h;
}
function goPage(p) { currentPage = p; renderPage(); window.scrollTo({top: 0, behavior: 'smooth'}); }

// -- statistics --
function renderStats() {
  if (!currentScanData) return;
  var d = currentScanData;
  var users = Object.values(d.users || {});

  var html = '';
  html += '<div class="stats">';
  html += '<div class="stat"><div class="stat-value">' + users.length + '</div><div class="stat-label">Total Users</div></div>';
  var actionable = users.filter(function(u) { return u.actionable; }).length;
  html += '<div class="stat"><div class="stat-value stat-value-danger">' + actionable + '</div><div class="stat-label">Actionable</div></div>';
  var withDiscord = users.filter(function(u) { return u.discord_accounts && u.discord_accounts.length > 0; }).length;
  html += '<div class="stat"><div class="stat-value">' + withDiscord + '</div><div class="stat-label">With Discord</div></div>';
  var avgConf = users.length ? Math.round(users.reduce(function(s,u) { return s + (u.confidence||0); }, 0) / users.length * 100) : 0;
  html += '<div class="stat"><div class="stat-value">' + avgConf + '%</div><div class="stat-label">Avg Confidence</div></div>';
  var activeCount = users.filter(function(u) { return u.isActive; }).length;
  html += '<div class="stat"><div class="stat-value">' + activeCount + '</div><div class="stat-label">Active Users</div></div>';
  html += '</div>';

  html += '<div class="chart-grid">';
  html += '<div class="chart-card"><h3>Flag Distribution</h3><canvas id="chartFlags"></canvas></div>';
  html += '<div class="chart-card"><h3>Users per Group</h3><canvas id="chartGroups"></canvas></div>';
  html += '<div class="chart-card"><h3>Confidence Distribution</h3><canvas id="chartConf"></canvas></div>';
  html += '</div>';

  document.getElementById('statsContent').innerHTML = html;

  var flagCounts = {};
  users.forEach(function(u) {
    var ft = u.flagType !== undefined ? u.flagType : -1;
    var name = (FLAG_MAP[ft] || {name:'Unknown'}).name;
    flagCounts[name] = (flagCounts[name] || 0) + 1;
  });
  if (flagChartInstance) flagChartInstance.destroy();
  flagChartInstance = new Chart(document.getElementById('chartFlags'), {
    type: 'doughnut',
    data: {
      labels: Object.keys(flagCounts),
      datasets: [{ data: Object.values(flagCounts),
        backgroundColor: Object.keys(flagCounts).map(function(n) {
          var entry = Object.values(FLAG_MAP).find(function(f) { return f.name === n; });
          return entry ? entry.color : '#6b7280';
        })
      }]
    },
    options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#999', font: {size:11} } } } }
  });

  var groupCounts = {};
  users.forEach(function(u) { var g = u.group_name || '?'; groupCounts[g] = (groupCounts[g]||0)+1; });
  var sortedGroups = Object.entries(groupCounts).sort(function(a,b) { return b[1]-a[1]; });
  if (groupChartInstance) groupChartInstance.destroy();
  groupChartInstance = new Chart(document.getElementById('chartGroups'), {
    type: 'bar',
    data: {
      labels: sortedGroups.map(function(g) { return g[0].length > 20 ? g[0].slice(0,20)+'…' : g[0]; }),
      datasets: [{ data: sortedGroups.map(function(g) { return g[1]; }), backgroundColor: 'rgba(99,102,241,.6)', borderRadius: 4 }]
    },
    options: { responsive: true, indexAxis: 'y', plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: '#999' }, grid: { color: '#222' } }, y: { ticks: { color: '#999', font: {size:10} }, grid: { display: false } } } }
  });

  var confBuckets = {'0-20%':0, '21-40%':0, '41-60%':0, '61-80%':0, '81-100%':0};
  users.forEach(function(u) {
    var c = Math.round((u.confidence||0)*100);
    if (c <= 20) confBuckets['0-20%']++;
    else if (c <= 40) confBuckets['21-40%']++;
    else if (c <= 60) confBuckets['41-60%']++;
    else if (c <= 80) confBuckets['61-80%']++;
    else confBuckets['81-100%']++;
  });
  if (confChartInstance) confChartInstance.destroy();
  confChartInstance = new Chart(document.getElementById('chartConf'), {
    type: 'bar',
    data: {
      labels: Object.keys(confBuckets),
      datasets: [{ data: Object.values(confBuckets), backgroundColor: ['#22c55e','#f59e0b','#f97316','#ef4444','#dc2626'], borderRadius: 4 }]
    },
    options: { responsive: true, plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: '#999' } }, y: { ticks: { color: '#999' }, grid: { color: '#222' } } }
    }
  });
}

// -- discord panel --
function renderDiscordPanel() {
  if (!currentScanData) return;
  var ids = currentScanData.discord_ids || [];
  document.getElementById('discordIdCount').textContent = ids.length;
  updateDiscordBox();
}

function setDiscordFormat(fmt) {
  discordFormat = fmt;
  document.querySelectorAll('.format-toggle button').forEach(function(b) { b.classList.remove('active'); });
  document.getElementById('fmt' + fmt.charAt(0).toUpperCase() + fmt.slice(1)).classList.add('active');
  updateDiscordBox();
}

function updateDiscordBox() {
  if (!currentScanData) return;
  var ids = currentScanData.discord_ids || [];
  var box = document.getElementById('discordIdBox');
  if (!ids.length) { box.textContent = 'No Discord IDs found.'; return; }
  switch (discordFormat) {
    case 'space': box.textContent = ids.join(' '); break;
    case 'newline': box.textContent = ids.join('\n'); break;
    case 'csv': box.textContent = ids.join(','); break;
    case 'json': box.textContent = JSON.stringify(ids, null, 2); break;
  }
}

function copyDiscordIds(e) {
  var text = document.getElementById('discordIdBox').textContent;
  var btn = e && e.target ? e.target : document.querySelector('[onclick*="copyDiscordIds"]');
  navigator.clipboard.writeText(text).then(function() {
    var orig = btn.textContent;
    btn.textContent = 'Copied!'; btn.classList.add('copied');
    setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 1500);
  });
}

function downloadDiscordTxt() {
  if (!currentScanData) return;
  var ids = currentScanData.discord_ids || [];
  var blob = new Blob([ids.join('\n')], {type:'text/plain'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'rotection_discord_' + (currentScanData.id || 'export') + '.txt';
  a.click();
}

function downloadDiscordJson() {
  if (!currentScanData) return;
  window.open(API_BASE + '/api/scans/' + currentScanData.id + '/discord-export', '_blank');
}

// -- user detail modal --
function showUserDetail(userId) {
  var u = allUsers.find(function(x) { return x.id == userId; });
  if (!u) return;
  var ft = FLAG_MAP[u.flagType] || {name:'Unknown',color:'#6b7280'};
  document.getElementById('modalTitle').textContent = u.name + ' — ' + (u.displayName || '');

  var h = '';
  h += '<div class="detail-row"><div class="detail-label">Roblox ID</div><div><a href="https://www.roblox.com/users/' + u.id + '/profile" target="_blank">' + u.id + '</a></div></div>';
  h += '<div class="detail-row"><div class="detail-label">Flag</div><div><span class="flag-badge" style="background:' + ft.color + '">' + ft.name + '</span> ' + (u.actionable ? '⚠️ Actionable' : '') + '</div></div>';
  h += '<div class="detail-row"><div class="detail-label">Confidence</div><div>' + (u.confidence ? Math.round(u.confidence*100)+'%' : 'N/A') + '</div></div>';
  h += '<div class="detail-row"><div class="detail-label">Group</div><div>' + esc(u.group_name||'?') + '</div></div>';
  h += '<div class="detail-row"><div class="detail-label">Active</div><div>' + (u.isActive ? 'Yes' : 'No') + '</div></div>';

  if (u.all_groups && u.all_groups.length) {
    h += '<div class="detail-row"><div class="detail-label">All Groups</div><div>';
    u.all_groups.forEach(function(g) { h += '<div class="detail-group-item">' + esc(g.name) + '</div>'; });
    h += '</div></div>';
  }

  if (u.reasons && u.reasons.length) {
    h += '<h4 class="modal-section-title">Violation Reasons</h4>';
    u.reasons.forEach(function(r) {
      h += '<div class="reason-card">';
      h += '<div class="reason-type">' + esc(r.type) + ' <span class="reason-conf">(' + Math.round((r.confidence||0)*100) + '%)</span></div>';
      if (r.message) h += '<div class="reason-msg">' + esc(r.message) + '</div>';
      if (r.evidence && r.evidence.length) {
        h += '<ul class="evidence-list">';
        r.evidence.forEach(function(ev) { h += '<li>' + esc(ev) + '</li>'; });
        h += '</ul>';
      }
      h += '</div>';
    });
  }

  if (u.discord_accounts && u.discord_accounts.length) {
    h += '<h4 class="modal-section-title">Linked Discord Accounts</h4>';
    u.discord_accounts.forEach(function(d) {
      h += '<div class="detail-discord-item"><span class="discord-id">' + safeDiscordId(d.id) + '</span>';
      if (d.sources && d.sources.length) h += ' <span class="text-muted text-xs">via ' + d.sources.join(', ') + '</span>';
      h += '</div>';
    });
  }

  if (u.alt_accounts && u.alt_accounts.length) {
    h += '<h4 class="modal-section-title">Known Alts</h4>';
    u.alt_accounts.forEach(function(a) {
      h += '<div class="detail-group-item"><a href="https://www.roblox.com/users/' + a.robloxUserId + '/profile" target="_blank">' + esc(a.robloxUsername) + '</a> (' + a.robloxUserId + ')</div>';
    });
  }

  document.getElementById('modalBody').innerHTML = h;
  document.getElementById('userModal').classList.add('show');
}

function closeModal() { document.getElementById('userModal').classList.remove('show'); }
document.getElementById('userModal').addEventListener('click', function(e) {
  if (e.target === document.getElementById('userModal')) closeModal();
});

// -- delete scan --
async function deleteScan(scanId, evt) {
  evt.stopPropagation();
  if (!confirm('Delete this scan from history?')) return;
  try {
    var resp = await fetch(API_BASE + '/api/scans/' + scanId, { method: 'DELETE' });
    if (resp.ok) loadHistory();
  } catch(e) {}
}

// -- history --
async function loadHistory() {
  var el = document.getElementById('historyList');
  el.innerHTML = '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading history...</p></div>';
  try {
    var resp = await fetch(API_BASE + '/api/scans');
    var scans = await resp.json().catch(function() { return []; });
    if (!scans || !scans.length) {
      el.innerHTML = '<div class="empty-state"><div class="icon">🕐</div><p>No scans yet.</p></div>';
      return;
    }
    var html = '';
    scans.forEach(function(s) {
      var ts = s.timestamp ? new Date(s.timestamp).toLocaleString() : 'Unknown';
      html += '<div class="history-item" onclick="loadScanResults(\'' + s.id + '\')">';
      html += '<div><strong>' + esc(s.primary_group) + '</strong><div class="history-meta">' + ts + ' · ' + s.groups_scanned + ' groups' + (s.include_allies ? ' (with allies)' : '') + '</div></div>';
      html += '<div class="history-right">';
      html += '<div class="history-stats">';
      html += '<div class="history-stat"><div class="history-stat-val">' + s.total_flagged + '</div><div class="history-stat-label">Flagged</div></div>';
      html += '<div class="history-stat"><div class="history-stat-val">' + s.total_discord_ids + '</div><div class="history-stat-label">Discord</div></div>';
      html += '</div>';
      html += '<button class="btn btn-danger btn-sm" onclick="deleteScan(\'' + s.id + '\', event)">🗑</button>';
      html += '</div></div>';
    });
    el.innerHTML = html;
  } catch(e) { console.error(e); }
}

// -- helpers --
function esc(s) { var d = document.createElement('div'); d.textContent = s||''; return d.innerHTML; }

// -- init --
async function init() {
  try {
    var resp = await fetch(API_BASE + '/api/progress');
    var state = await resp.json().catch(function() { return null; });
    if (!state) return;
    if (state.status === 'scanning') {
      document.getElementById('scanProgress').style.display = 'block';
      document.getElementById('btnScan').disabled = true;
      document.getElementById('btnScan').textContent = 'Scan in Progress';
      document.getElementById('btnScanSEA').disabled = true;
      document.getElementById('btnScanSEA').textContent = 'Scan in Progress...';
      startProgressStream();
    } else if (state.status === 'done' && state.scan_id) {
      loadScanResults(state.scan_id);
    }
  } catch(e) {}
  try {
    var resp2 = await fetch(API_BASE + '/api/scans');
    var scans = await resp2.json().catch(function() { return []; });
    if (scans && scans.length > 0 && !currentScanData) {
      loadScanResults(scans[0].id);
    }
  } catch(e) {}
}
init();
