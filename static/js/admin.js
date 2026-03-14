// Admin Panel Script

// ──────────────────── User detail modal ────────────────────
function showUserDetail(userId) {
  var u = allUsers.find(function(x) { return x.id == userId; });
  if (!u) return;
  var ft = FLAG_MAP[u.flagType] || {name:'Unknown',color:'#6b7280'};
  document.getElementById('modalTitle').textContent = u.name + ' — ' + (u.displayName || '');
  var stObj = currentScanStatuses[String(u.id)];
  var uStatus = stObj ? stObj.status : 'Pending Review';
  var stCss = STATUS_CSS[uStatus] || 'ust-pending-review';

  var h = '';
  h += '<div class="detail-row"><div class="detail-label">Roblox ID</div><div><a href="https://www.roblox.com/users/' + u.id + '/profile" target="_blank">' + u.id + '</a></div></div>';
  h += '<div class="detail-row"><div class="detail-label">Flag</div><div><span class="flag-badge" style="background:' + ft.color + '">' + ft.name + '</span> ' + (u.actionable ? '⚠️ Actionable' : '') + '</div></div>';
  h += '<div class="detail-row"><div class="detail-label">Confidence</div><div>' + (u.confidence ? Math.round(u.confidence*100)+'%' : 'N/A') + '</div></div>';
  h += '<div class="detail-row"><div class="detail-label">Status</div><div><span class="user-status-badge ' + stCss + '">' + esc(uStatus) + '</span>' + (stObj && stObj.set_by ? ' <span class="text-muted text-xs">by ' + esc(stObj.set_by) + '</span>' : '') + '</div></div>';
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
      h += '<div class="reason-card"><div class="reason-type">' + esc(r.type) + ' <span class="reason-conf">(' + Math.round((r.confidence||0)*100) + '%)</span></div>';
      if (r.message) h += '<div class="reason-msg">' + esc(r.message) + '</div>';
      if (r.evidence && r.evidence.length) { h += '<ul class="evidence-list">'; r.evidence.forEach(function(ev) { h += '<li>' + esc(ev) + '</li>'; }); h += '</ul>'; }
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

// ──────────────────── Delete scan ────────────────────
async function deleteScan(scanId, evt) {
  evt.stopPropagation();
  if (!confirm('Delete this scan from history?')) return;
  try {
    var resp = await fetch(API_BASE + '/api/scans/' + scanId, { method: 'DELETE' });
    if (resp.ok) loadHistory();
    else { var d = await resp.json().catch(function() { return {}; }); alert(d.error || 'Cannot delete'); }
  } catch(e) {}
}

// ──────────────────── History ────────────────────
async function loadHistory() {
  var el = document.getElementById('historyList');
  el.innerHTML = '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading history...</p></div>';
  try {
    var resp = await fetch(API_BASE + '/api/scans');
    var scans = await resp.json().catch(function() { return []; });
    if (!scans || !scans.length) { el.innerHTML = '<div class="empty-state"><div class="icon">🕐</div><p>No scans yet.</p></div>'; return; }
    var html = '';
    scans.forEach(function(s) {
      var ts = s.timestamp ? new Date(s.timestamp).toLocaleString() : 'Unknown';
      html += '<div class="history-item" onclick="loadScanResults(\'' + s.id + '\')">';
      html += '<div><strong>' + esc(s.primary_group) + '</strong><div class="history-meta">' + ts + ' · ' + s.groups_scanned + ' groups' + (s.include_allies ? ' (with allies)' : '') + '</div></div>';
      html += '<div class="history-right"><div class="history-stats">';
      html += '<div class="history-stat"><div class="history-stat-val">' + s.total_flagged + '</div><div class="history-stat-label">Flagged</div></div>';
      html += '<div class="history-stat"><div class="history-stat-val">' + s.total_discord_ids + '</div><div class="history-stat-label">Discord</div></div>';
      html += '</div>';
      if (isAdmin()) html += '<button class="btn btn-danger btn-sm" onclick="deleteScan(\'' + s.id + '\', event)">🗑</button>';
      html += '</div></div>';
    });
    el.innerHTML = html;
  } catch(e) { console.error(e); }
}

// ──────────────────── Queue ────────────────────
async function loadQueue() {
  var el = document.getElementById('queueList');
  el.innerHTML = '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading queue...</p></div>';
  try {
    var resp = await fetch(API_BASE + '/api/queue');
    var queue = await resp.json().catch(function() { return []; });
    if (!queue || !queue.length) { el.innerHTML = '<div class="empty-state"><div class="icon">📋</div><p>No scans in queue. All clear!</p></div>'; return; }
    var html = '';
    queue.forEach(function(q) {
      var stClass = q.status === 'running' ? 'qi-status-running' : 'qi-status-queued';
      html += '<div class="queue-item">';
      html += '<div class="qi-pos">#' + q.position + '</div>';
      html += '<div class="qi-info"><strong>Group ' + q.group_id + '</strong>';
      html += '<div class="text-muted text-xs">By ' + esc(q.requested_by) + ' · ' + (q.include_allies ? 'with allies' : 'no allies') + '</div></div>';
      html += '<span class="qi-status ' + stClass + '">' + q.status.toUpperCase() + '</span>';
      html += '</div>';
    });
    el.innerHTML = html;
  } catch(e) { console.error(e); }
}

// ──────────────────── Admin Panel ────────────────────
async function loadAdminUsers() {
  var el = document.getElementById('adminUserList');
  el.innerHTML = '<div class="empty-state"><div class="icon pulse">⏳</div><p>Loading users...</p></div>';
  try {
    var resp = await fetch(API_BASE + '/api/admin/users');
    if (!resp.ok) { el.innerHTML = '<div class="empty-state"><p>Access denied</p></div>'; return; }
    var users = await resp.json();
    if (!users.length) { el.innerHTML = '<div class="empty-state"><p>No users registered yet.</p></div>'; return; }
    var html = '';
    users.forEach(function(u) {
      html += '<div class="admin-user-row">';
      html += '<div>';
      html += '<div class="au-name">' + esc(u.username);
      if (u.is_admin) html += ' <span class="admin-badge admin-badge-admin">ADMIN</span>';
      if (u.admin_confirmed && !u.is_admin) html += ' <span class="admin-badge admin-badge-confirmed">CONFIRMED</span>';
      if (!u.admin_confirmed && !u.is_admin && u.roles.includes('Division Administrator')) html += ' <span class="admin-badge admin-badge-pending">PENDING DA</span>';
      if (u.division_name) {
        html += ' <span class="admin-badge ' + (u.division_confirmed ? 'admin-badge-confirmed' : 'admin-badge-pending') + '">' + esc(u.division_name) + '</span>';
      }
      html += '</div>';
      html += '<div class="au-roles">' + u.roles.join(', ') + '</div>';
      if (u.divisions_moderating && u.divisions_moderating.length) {
        html += '<div style="margin-top:4px">';
        var confirmed = u.divisions_mod_confirmed || [];
        var confirmedIds = confirmed.map(function(d) { return d.id; });
        u.divisions_moderating.forEach(function(d) {
          var isConf = confirmedIds.indexOf(d.id) !== -1;
          html += '<span class="div-confirm-chip ' + (isConf ? 'confirmed' : 'pending') + '">' + (isConf ? '✓' : '⏳') + ' ' + esc(d.name) + '</span>';
        });
        html += '</div>';
      }
      html += '<div class="au-created">Joined: ' + (u.created_at || '?') + '</div>';
      html += '</div>';
      html += '<div class="au-actions">';
      if (!u.is_admin) {
        html += '<button class="btn btn-secondary btn-sm" onclick="openAdminEditModal(' + u.id + ')">Edit</button>';
        html += '<button class="btn btn-danger btn-sm" onclick="adminDeleteUser(' + u.id + ',\'' + esc(u.username) + '\')">Delete</button>';
      }
      html += '</div>';
      html += '</div>';
    });
    el.innerHTML = html;
  } catch(e) { console.error(e); }
}

var _adminEditUserId = null;
async function openAdminEditModal(userId) {
  _adminEditUserId = userId;
  try {
    var resp = await fetch(API_BASE + '/api/admin/users');
    var users = await resp.json();
    var u = users.find(function(x) { return x.id === userId; });
    if (!u) return;

    document.getElementById('adminModalTitle').textContent = 'Edit — ' + u.username;
    var h = '';

    h += '<div class="admin-form-group"><label>Roles</label><div class="admin-role-chips" id="adminRoleChips">';
    ROLE_OPTIONS.forEach(function(r) {
      var sel = u.roles.indexOf(r) !== -1 ? ' selected' : '';
      h += '<div class="admin-role-chip' + sel + '" data-role="' + esc(r) + '" onclick="toggleAdminRole(this)">' + esc(r) + '</div>';
    });
    h += '</div></div>';

    if (u.roles.includes('Division Administrator')) {
      h += '<div class="admin-confirm-row"><div class="admin-confirm-label">Division Administrator Confirmed</div>';
      h += '<button class="admin-toggle ' + (u.admin_confirmed ? 'on' : 'off') + '" id="toggleDA" onclick="toggleAdminConfirm(this,\'admin_confirmed\',' + u.id + ')"></button></div>';
    }

    if (u.roles.includes('Division Leader') && u.division_name) {
      h += '<div class="admin-confirm-row"><div class="admin-confirm-label">Division Leader: ' + esc(u.division_name) + ' (ID: ' + (u.division_group_id||'?') + ')</div>';
      h += '<button class="admin-toggle ' + (u.division_confirmed ? 'on' : 'off') + '" id="toggleDL" onclick="toggleAdminConfirm(this,\'division_confirmed\',' + u.id + ')"></button></div>';
    }

    if (u.roles.includes('Moderator at a division') && u.divisions_moderating && u.divisions_moderating.length) {
      h += '<div class="admin-form-group"><label>Confirm Division Moderator Access</label>';
      var confirmed = u.divisions_mod_confirmed || [];
      var confirmedIds = confirmed.map(function(d) { return d.id; });
      u.divisions_moderating.forEach(function(d) {
        var isConf = confirmedIds.indexOf(d.id) !== -1;
        h += '<div class="admin-confirm-row"><div class="admin-confirm-label">' + esc(d.name) + '</div>';
        h += '<button class="admin-toggle ' + (isConf ? 'on' : 'off') + '" data-div-id="' + d.id + '" data-div-name="' + esc(d.name) + '" onclick="toggleModDivConfirm(this,' + u.id + ')"></button></div>';
      });
      h += '</div>';
    }

    h += '<button class="btn btn-primary" style="margin-top:12px" onclick="saveAdminRoles(' + u.id + ')">Save Roles</button>';

    document.getElementById('adminModalBody').innerHTML = h;
    document.getElementById('adminUserModal').classList.add('show');
  } catch(e) { console.error(e); }
}

function closeAdminModal() { document.getElementById('adminUserModal').classList.remove('show'); }

function toggleAdminRole(el) {
  el.classList.toggle('selected');
}

async function toggleAdminConfirm(btn, field, userId) {
  var isOn = btn.classList.contains('on');
  var newVal = !isOn;
  var body = {}; body[field] = newVal;
  try {
    var resp = await fetch(API_BASE + '/api/admin/users/' + userId, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    if (resp.ok) { btn.classList.toggle('on'); btn.classList.toggle('off'); loadAdminUsers(); }
  } catch(e) {}
}

async function toggleModDivConfirm(btn, userId) {
  var allToggles = document.querySelectorAll('[data-div-id]');
  var wasOn = btn.classList.contains('on');
  if (wasOn) { btn.classList.remove('on'); btn.classList.add('off'); }
  else { btn.classList.add('on'); btn.classList.remove('off'); }

  var confirmed = [];
  allToggles.forEach(function(t) {
    if (t.classList.contains('on')) {
      confirmed.push({ id: parseInt(t.dataset.divId), name: t.dataset.divName });
    }
  });
  try {
    var resp = await fetch(API_BASE + '/api/admin/users/' + userId, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ divisions_mod_confirmed: confirmed })
    });
    if (resp.ok) loadAdminUsers();
  } catch(e) {}
}

async function saveAdminRoles(userId) {
  var chips = document.querySelectorAll('#adminRoleChips .admin-role-chip.selected');
  var roles = [];
  chips.forEach(function(c) { roles.push(c.dataset.role); });
  try {
    var resp = await fetch(API_BASE + '/api/admin/users/' + userId, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ roles: roles })
    });
    if (resp.ok) { closeAdminModal(); loadAdminUsers(); }
    else { var d = await resp.json().catch(function() { return {}; }); alert(d.error || 'Failed to save'); }
  } catch(e) { alert('Network error'); }
}

async function adminDeleteUser(userId, username) {
  if (!confirm('Delete user "' + username + '"? This cannot be undone.')) return;
  try {
    var resp = await fetch(API_BASE + '/api/admin/users/' + userId, { method: 'DELETE' });
    if (resp.ok) loadAdminUsers();
    else { var d = await resp.json().catch(function() { return {}; }); alert(d.error || 'Failed to delete'); }
  } catch(e) {}
}
