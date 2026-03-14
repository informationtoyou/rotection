// Statistics charts using chart.js

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
  users.forEach(function(u) { var ft = u.flagType !== undefined ? u.flagType : -1; var name = (FLAG_MAP[ft] || {name:'Unknown'}).name; flagCounts[name] = (flagCounts[name] || 0) + 1; });
  if (flagChartInstance) flagChartInstance.destroy();
  flagChartInstance = new Chart(document.getElementById('chartFlags'), {
    type: 'doughnut', data: { labels: Object.keys(flagCounts), datasets: [{ data: Object.values(flagCounts),
      backgroundColor: Object.keys(flagCounts).map(function(n) { var e = Object.values(FLAG_MAP).find(function(f) { return f.name === n; }); return e ? e.color : '#6b7280'; }) }] },
    options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { color: '#999', font: {size:11} } } } }
  });

  var groupCounts = {};
  users.forEach(function(u) { var g = u.group_name || '?'; groupCounts[g] = (groupCounts[g]||0)+1; });
  var sortedGroups = Object.entries(groupCounts).sort(function(a,b) { return b[1]-a[1]; });
  if (groupChartInstance) groupChartInstance.destroy();
  groupChartInstance = new Chart(document.getElementById('chartGroups'), {
    type: 'bar', data: { labels: sortedGroups.map(function(g) { return g[0].length > 20 ? g[0].slice(0,20)+'…' : g[0]; }),
      datasets: [{ data: sortedGroups.map(function(g) { return g[1]; }), backgroundColor: 'rgba(99,102,241,.6)', borderRadius: 4 }] },
    options: { responsive: true, indexAxis: 'y', plugins: { legend: { display: false } },
      scales: { x: { ticks: { color: '#999' }, grid: { color: '#222' } }, y: { ticks: { color: '#999', font: {size:10} }, grid: { display: false } } } }
  });

  var confBuckets = {'0-20%':0, '21-40%':0, '41-60%':0, '61-80%':0, '81-100%':0};
  users.forEach(function(u) { var c = Math.round((u.confidence||0)*100); if (c <= 20) confBuckets['0-20%']++; else if (c <= 40) confBuckets['21-40%']++; else if (c <= 60) confBuckets['41-60%']++; else if (c <= 80) confBuckets['61-80%']++; else confBuckets['81-100%']++; });
  if (confChartInstance) confChartInstance.destroy();
  confChartInstance = new Chart(document.getElementById('chartConf'), {
    type: 'bar', data: { labels: Object.keys(confBuckets), datasets: [{ data: Object.values(confBuckets), backgroundColor: ['#22c55e','#f59e0b','#f97316','#ef4444','#dc2626'], borderRadius: 4 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#999' } }, y: { ticks: { color: '#999' }, grid: { color: '#222' } } } }
  });
}
