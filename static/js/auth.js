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
    // show pending banner if needed
    var needsConfirm = false;
    if (currentUser.roles.includes('Division Administrator') && !currentUser.admin_confirmed) needsConfirm = true;
    if (currentUser.roles.includes('Division Leader') && !currentUser.division_confirmed) needsConfirm = true;
    if (currentUser.roles.includes('Moderator at a division')) {
      var confirmed = currentUser.divisions_mod_confirmed || [];
      var requested = currentUser.divisions_moderating || [];
      if (confirmed.length < requested.length) needsConfirm = true;
    }
    if (needsConfirm) {
      document.getElementById('pendingBanner').style.display = 'flex';
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
