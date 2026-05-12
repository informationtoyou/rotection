// Authentication script

async function doLogout() {
  try { await fetch(API_BASE + '/api/auth/logout', { method: 'POST' }); } catch(e) {}
  window.location.href = '/login';
}

async function loadCurrentUser() {
  try {
    var resp = await fetch(API_BASE + '/api/auth/me');
    if (!resp.ok) { window.location.href = '/login'; return null; }
    var data = await resp.json();
    currentUser = data.user;
    // update UI
    document.getElementById('userBadge').style.display = 'flex';
    document.getElementById('userName').textContent = currentUser.username;
    document.getElementById('userRoles').textContent = currentUser.roles.join(', ');
    // show admin tab
    if (currentUser.is_admin) {
      document.getElementById('adminTab').style.display = '';
    }
    var isDivLeaderRole = currentUser.roles.includes('Division Leader');
    if (isDivLeaderRole) {
      await loadRobloxStatus();
    }

    // show pending banner if needed
    var needsConfirm = false;
    if (currentUser.roles.includes('Division Administrator') && !currentUser.admin_confirmed) needsConfirm = true;
    if (isDivLeaderRole && !currentUser.division_confirmed) needsConfirm = true;
    if (currentUser.roles.includes('Moderator at a division')) {
      var confirmed = currentUser.divisions_mod_confirmed || [];
      var requested = currentUser.divisions_moderating || [];
      if (confirmed.length < requested.length) needsConfirm = true;
    }
    if (needsConfirm) {
      var banner = document.getElementById('pendingBanner');
      var msgEl = document.getElementById('pendingMessage');
      var verifyBtn = document.getElementById('verifyRobloxBtn');
      banner.style.display = 'flex';
      if (isDivLeaderRole && !currentUser.division_confirmed && robloxConnection && robloxConnection.oauth_configured) {
        msgEl.textContent = 'Your Division Leader access is pending. You can verify instantly with Roblox.';
        verifyBtn.style.display = 'inline-flex';
      } else {
        verifyBtn.style.display = 'none';
      }
    }
    // show division quick scan button for Division Leaders (confirmed)
    if (currentUser.division_group_id && currentUser.division_confirmed) {
      document.getElementById('divisionQuickScan').style.display = 'block';
      document.getElementById('btnScanMyDivision').textContent = '🎖️ Scan ' + (currentUser.division_name || 'My Division');
    }
    // show moderated divisions quick scan button for Division Moderators (confirmed)
    if (currentUser.divisions_mod_confirmed && currentUser.divisions_mod_confirmed.length > 0) {
      document.getElementById('modDivisionsQuickScan').style.display = 'block';
      var modNames = currentUser.divisions_mod_confirmed.map(function(d) { return d.name || ('Group ' + d.id); });
      document.getElementById('btnScanModDivisions').textContent = '🛡️ Scan My Moderated Divisions (' + modNames.length + ')';
    }
    return currentUser;
  } catch(e) {
    window.location.href = '/login';
    return null;
  }
}

async function loadRobloxStatus() {
  try {
    var resp = await fetch(API_BASE + '/api/roblox/status');
    if (!resp.ok) { robloxConnection = null; return; }
    robloxConnection = await resp.json();
  } catch(e) {
    robloxConnection = null;
  }
}

function startRobloxVerify() {
  window.location.href = '/api/roblox/oauth/start';
}
