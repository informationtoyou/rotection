// Init, tab wiring, listeners

// ──────────────────── Tabs ────────────────────
document.querySelectorAll('.tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
    tab.classList.add('active');
    document.getElementById('panel-' + tab.dataset.tab).classList.add('active');
    if (tab.dataset.tab === 'history') loadHistory();
    if (tab.dataset.tab === 'queue') loadQueue();
    if (tab.dataset.tab === 'admin' && isAdmin()) {
      loadAdminUsers();
      try {
        // load audit with selected limit (default 200)
        var limitEl = document.getElementById('auditLimit');
        var lim = limitEl ? parseInt(limitEl.value) : 200;
        loadAudit(lim);
      } catch(e) {}
    }
  });
});

// ──────────────────── Modal listeners ────────────────────
document.getElementById('userModal').addEventListener('click', function(e) {
  if (e.target === document.getElementById('userModal')) closeModal();
});
document.getElementById('adminUserModal').addEventListener('click', function(e) {
  if (e.target === document.getElementById('adminUserModal')) closeAdminModal();
});

// ──────────────────── Init ────────────────────
async function init() {
  var user = await loadCurrentUser();
  if (!user) return;

  startDeployPolling();

  try {
    var resp = await fetch(API_BASE + '/api/progress');
    var state = await resp.json().catch(function() { return null; });
    if (!state) return;
    if (state.status === 'scanning') {
      document.getElementById('scanProgress').style.display = 'block';
      startProgressStream();
    } else if (state.status === 'done' && state.scan_id) {
      loadScanResults(state.scan_id);
    }
  } catch(e) {}

  try {
    var resp2 = await fetch(API_BASE + '/api/scans');
    var scans = await resp2.json().catch(function() { return []; });
    if (scans && scans.length > 0 && !currentScanData) {
      var seaScan = scans.find(function(s) {
        return s.primary_group_id === SEA_GROUP_ID && s.include_allies;
      });
      var defaultScan = seaScan || scans[0];
      loadScanResults(defaultScan.id);
    }
  } catch(e) {}
}
init();
