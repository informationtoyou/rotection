// Pagination and filtering and loading for scans

var _filterDebounceTimer = null;
function applyFiltersDebounced() {
  clearTimeout(_filterDebounceTimer);
  _filterDebounceTimer = setTimeout(applyFilters, 150);
}

async function loadScanResults(scanId) {
  document.getElementById('resultsContent').innerHTML = '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading scan results...</p></div>';
  document.getElementById('statsContent').innerHTML = '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading statistics...</p></div>';
  try {
    var resp = await fetch(API_BASE + '/api/scans/' + scanId);
    if (!resp.ok) {
      var err = await resp.json().catch(function() { return {}; });
      document.getElementById('resultsContent').innerHTML = '<div class="empty-state"><div class="icon">🚫</div><p>' + esc(err.error || 'Failed to load scan') + '</p></div>';
      return;
    }
    currentScanData = await resp.json();
    // load statuses
    try {
      var sResp = await fetch(API_BASE + '/api/user-statuses/' + scanId);
      if (sResp.ok) currentScanStatuses = await sResp.json();
      else currentScanStatuses = {};
    } catch(e) { currentScanStatuses = {}; }
    renderResults();
    renderStats();
    renderDiscordPanel();
    document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
    document.querySelector('[data-tab="results"]').classList.add('active');
    document.getElementById('panel-results').classList.add('active');
  } catch(e) { console.error(e); }
}

function renderResults() {
  if (!currentScanData) return;
  var d = currentScanData;
  allUsers = Object.values(d.users || {});
  currentPage = 1;

  var groupSet = new Map();
  var flagSet = new Set();
  allUsers.forEach(function(u) {
    var gn = u.group_name || 'Unknown';
    groupSet.set(gn, (groupSet.get(gn) || 0) + 1);
    flagSet.add(u.flagType !== undefined ? u.flagType : -1);
  });
  var groups = Array.from(groupSet.entries()).sort(function(a,b) { return b[1] - a[1]; });

  var html = '';
  html += '<div class="stats">';
  html += '<div class="stat"><div class="stat-value">' + (d.total_flagged||0) + '</div><div class="stat-label">Flagged Users</div></div>';
  html += '<div class="stat"><div class="stat-value">' + (d.total_discord_ids||0) + '</div><div class="stat-label">Discord IDs</div></div>';
  html += '<div class="stat"><div class="stat-value">' + Object.keys(d.groups||{}).length + '</div><div class="stat-label">Groups Scanned</div></div>';
  html += '<div class="stat"><div class="stat-value small">' + esc(d.primary_group_name||'?') + '</div><div class="stat-label">Primary Group</div></div>';
  var ts = d.timestamp ? new Date(d.timestamp).toLocaleString() : '?';
  html += '<div class="stat"><div class="stat-value small">' + ts + '</div><div class="stat-label">Scan Time</div></div>';
  html += '</div>';

  html += '<div class="card"><h2>Group Filter</h2><div class="group-nav">';
  html += '<div class="group-chip active" data-group="" onclick="filterByGroup(this)">All Groups <span class="count">' + allUsers.length + '</span></div>';
  var primaryGroupName = d.primary_group_name || '';
  for (var gi2 = 0; gi2 < groups.length; gi2++) {
    var gn = groups[gi2][0], cnt = groups[gi2][1];
    var isPrimary = gn === primaryGroupName;
    html += '<div class="group-chip' + (isPrimary ? ' primary' : '') + '" data-group="' + esc(gn) + '" onclick="filterByGroup(this)">' + esc(gn) + ' <span class="count">' + cnt + '</span></div>';
  }
  html += '</div></div>';

  html += '<div class="card"><h2>Filters</h2><div class="filter-bar">';
  html += '<input type="text" class="search-input" id="searchInput" placeholder="Search username, display name, or ID..." oninput="applyFiltersDebounced()">';
  html += '<select id="filterFlag" onchange="applyFilters()"><option value="">All Flags</option>';
  Object.entries(FLAG_MAP).forEach(function(entry) {
    var k = entry[0], v = entry[1];
    if (flagSet.has(parseInt(k))) html += '<option value="' + k + '">' + v.name + '</option>';
  });
  html += '</select>';
  html += '<select id="filterStatus" onchange="applyFilters()"><option value="">All Statuses</option>';
  var statusOpts = canSeeInternalStatuses() ? ALL_STATUSES : ['SEA Banned','False Positive'];
  statusOpts.forEach(function(s) { html += '<option value="' + s + '">' + s + '</option>'; });
  html += '</select>';
  html += '<div class="range-group"><label class="filter-label">Min conf:</label>';
  html += '<input type="range" id="filterConfMin" min="0" max="100" value="0" oninput="applyFilters();document.getElementById(\'confMinVal\').textContent=this.value+\'%\'">';
  html += '<span id="confMinVal" class="filter-label" style="min-width:30px">0%</span></div>';
  html += '<label class="filter-check-label"><input type="checkbox" id="filterActionable" onchange="applyFilters()" class="accent-check"> Actionable only</label>';
  html += '<label class="filter-check-label"><input type="checkbox" id="filterHasDiscord" onchange="applyFilters()" class="accent-check"> Has Discord</label>';
  html += '<label class="filter-check-label"><input type="checkbox" id="filterHRHC" onchange="applyFilters()" class="accent-check"> HR/HC Only</label>';
  html += '<label class="filter-check-label"><input type="checkbox" id="filterExcludeHRHC" onchange="applyFilters()" class="accent-check"> Exclude HR/HC</label>';
  html += '</div><div class="filter-summary" id="filterSummary"></div></div>';

  html += '<div class="card"><h2>Users <span id="resultCount" class="result-count"></span></h2>';
  html += '<div class="pagination" id="paginationTop"></div>';
  html += '<div class="tbl-wrap"><table><thead><tr>';
  html += '<th onclick="doSort(\'name\')" id="th-name">User</th>';
  html += '<th onclick="doSort(\'flagType\')" id="th-flagType">Flag</th>';
  html += '<th onclick="doSort(\'confidence\')" id="th-confidence">Confidence</th>';
  html += '<th onclick="doSort(\'group_name\')" id="th-group_name">Group</th>';
  html += '<th>Reasons</th><th>Discord</th>';
  html += '<th>Status</th>';
  html += '<th onclick="doSort(\'isActive\')" id="th-isActive">Active</th>';
  html += '<th>Details</th>';
  html += '</tr></thead><tbody id="resultsBody"></tbody></table></div>';
  html += '<div class="pagination" id="paginationBottom"></div></div>';

  document.getElementById('resultsContent').innerHTML = html;
  applyFilters();
}

function filterByGroup(el) {
  document.querySelectorAll('.group-chip').forEach(function(c) { c.classList.remove('active'); });
  el.classList.add('active');
  applyFilters();
}

function applyFilters() {
  if (!allUsers.length) return;
  var search = (document.getElementById('searchInput') ? document.getElementById('searchInput').value : '').toLowerCase();
  var activeChip = document.querySelector('.group-chip.active');
  var activeGroup = activeChip ? (activeChip.dataset.group || '') : '';
  var flag = document.getElementById('filterFlag') ? document.getElementById('filterFlag').value : '';
  var statusFilter = document.getElementById('filterStatus') ? document.getElementById('filterStatus').value : '';
  var confMin = parseInt(document.getElementById('filterConfMin') ? document.getElementById('filterConfMin').value : '0');
  var actionable = document.getElementById('filterActionable') ? document.getElementById('filterActionable').checked : false;
  var hasDiscord = document.getElementById('filterHasDiscord') ? document.getElementById('filterHasDiscord').checked : false;
  var hrhcOnly = document.getElementById('filterHRHC') ? document.getElementById('filterHRHC').checked : false;
  var excludeHrhc = document.getElementById('filterExcludeHRHC') ? document.getElementById('filterExcludeHRHC').checked : false;

  filteredUsers = allUsers.filter(function(u) {
    if (search && !(u.name||'').toLowerCase().includes(search) && !String(u.id).includes(search) && !(u.displayName||'').toLowerCase().includes(search)) return false;
    if (activeGroup && u.group_name !== activeGroup) return false;
    if (flag !== '' && u.flagType !== parseInt(flag)) return false;
    var conf = u.confidence ? Math.round(u.confidence * 100) : 0;
    if (conf < confMin) return false;
    if (actionable && !u.actionable) return false;
    if (hasDiscord && (!u.discord_accounts || u.discord_accounts.length === 0)) return false;
    if (hrhcOnly && !u.is_sea_hrhc) return false;
    if (excludeHrhc && u.is_sea_hrhc) return false;
    if (statusFilter) {
      var st = currentScanStatuses[String(u.id)];
      var uStatus = st ? st.status : 'Pending Review';
      if (uStatus !== statusFilter) return false;
    }
    return true;
  });

  filteredUsers.sort(function(a, b) {
    var va = a[sortCol] != null ? a[sortCol] : '';
    var vb = b[sortCol] != null ? b[sortCol] : '';
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    return va < vb ? -1 * sortDir : va > vb ? 1 * sortDir : 0;
  });

  document.querySelectorAll('th').forEach(function(th) { th.classList.remove('sorted'); });
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

  document.getElementById('resultCount').textContent = 'Showing ' + (total ? start+1 : 0) + '–' + end + ' of ' + total + ' (' + allUsers.length + ' total)';
  document.getElementById('filterSummary').textContent = total === allUsers.length ? '' : total + ' users match your filters out of ' + allUsers.length + ' total';

  var pagHtml = buildPagination(totalPages);
  document.getElementById('paginationTop').innerHTML = pagHtml;
  document.getElementById('paginationBottom').innerHTML = pagHtml;

  var body = document.getElementById('resultsBody');
  var html = '';
  var showStatusSelect = canSetStatus();

  page.forEach(function(u) {
    var ft = FLAG_MAP[u.flagType] || {name:'Unknown',color:'#6b7280'};
    var conf = u.confidence ? Math.round(u.confidence * 100) : 0;
    var confColor = conf >= 80 ? 'var(--red)' : conf >= 50 ? 'var(--orange)' : 'var(--yellow)';
    var thumb = safeThumbnail(u.thumbnailUrl);
    var discords = (u.discord_accounts || []).slice(0,3).map(function(d) { return '<span class="discord-id">' + safeDiscordId(d.id) + '</span>'; }).join(' ');
    var moreDiscords = (u.discord_accounts || []).length > 3 ? '<span class="text-muted text-xs">+' + (u.discord_accounts.length-3) + '</span>' : '';
    var reasonCount = (u.reasons || []).length;
    var stObj = currentScanStatuses[String(u.id)];
    var uStatus = stObj ? stObj.status : 'Pending Review';
    var stCss = STATUS_CSS[uStatus] || 'ust-pending-review';

    html += '<tr>';
    html += '<td>' + (thumb ? '<img class="avatar" src="' + thumb + '" loading="lazy" onerror="this.style.display=\'none\'">' : '') + '<strong>' + esc(u.name) + '</strong>' + (u.is_sea_hrhc ? ' <span class="hrhc-tag">HR/HC</span>' : '') + '<br><span class="text-muted text-xs">' + esc(u.displayName||'') + ' · ' + u.id + '</span></td>';
    html += '<td><span class="flag-badge" style="background:' + ft.color + '">' + ft.name + '</span></td>';
    html += '<td><div class="confidence-bar"><div class="confidence-fill" style="width:' + conf + '%;background:' + confColor + '"></div></div>' + conf + '%</td>';
    html += '<td class="text-xs">' + esc(u.group_name||'?') + '</td>';
    html += '<td class="text-xs">' + (reasonCount > 0 ? '<span class="text-danger">' + reasonCount + ' reason' + (reasonCount>1?'s':'') + '</span>' : '—') + '</td>';
    html += '<td>' + discords + (moreDiscords || (!discords ? '<span class="text-muted text-xs">None</span>' : '')) + '</td>';

    // status column
    if (showStatusSelect) {
      html += '<td><select class="status-select" onchange="setUserStatus(' + u.id + ',this.value)">';
      ALL_STATUSES.forEach(function(s) { html += '<option value="' + s + '"' + (uStatus === s ? ' selected' : '') + '>' + s + '</option>'; });
      html += '</select></td>';
    } else {
      html += '<td><span class="user-status-badge ' + stCss + '">' + esc(uStatus) + '</span></td>';
    }

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
  h += '</select><div class="page-btns">';
  h += '<button onclick="goPage(1)" ' + (currentPage===1?'disabled':'') + '>«</button>';
  h += '<button onclick="goPage(' + (currentPage-1) + ')" ' + (currentPage===1?'disabled':'') + '>‹</button>';
  var range = 2, startP = Math.max(1, currentPage - range), endP = Math.min(totalPages, currentPage + range);
  if (startP > 1) h += '<button disabled>…</button>';
  for (var i = startP; i <= endP; i++) h += '<button onclick="goPage(' + i + ')" class="' + (i===currentPage?'active':'') + '">' + i + '</button>';
  if (endP < totalPages) h += '<button disabled>…</button>';
  h += '<button onclick="goPage(' + (currentPage+1) + ')" ' + (currentPage===totalPages?'disabled':'') + '>›</button>';
  h += '<button onclick="goPage(' + totalPages + ')" ' + (currentPage===totalPages?'disabled':'') + '>»</button>';
  h += '</div></div>';
  return h;
}

function goPage(p) { currentPage = p; renderPage(); window.scrollTo({top: 0, behavior: 'smooth'}); }

async function setUserStatus(robloxId, status) {
  if (!currentScanData) return;
  var u = allUsers.find(function(x) { return x.id == robloxId; });
  var discordIds = (u && u.discord_accounts) ? u.discord_accounts.map(function(d) { return d.id; }) : [];
  try {
    var resp = await fetch(API_BASE + '/api/user-status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ roblox_id: robloxId, status: status, discord_ids: discordIds })
    });
    var data = await resp.json();
    if (!resp.ok) { alert(data.error || 'Failed to set status'); return; }
    currentScanStatuses[String(robloxId)] = { status: status, set_by: currentUser.username, discord_ids: discordIds };
  } catch(e) { alert('Network error'); }
}
