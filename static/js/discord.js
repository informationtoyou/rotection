// Discord Export

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
  var btn = e && e.target ? e.target : null;
  navigator.clipboard.writeText(text).then(function() {
    if (btn) { var orig = btn.textContent; btn.textContent = 'Copied!'; btn.classList.add('copied'); setTimeout(function() { btn.textContent = orig; btn.classList.remove('copied'); }, 1500); }
  });
}

function downloadDiscordTxt() {
  if (!currentScanData) return;
  var ids = currentScanData.discord_ids || [];
  var blob = new Blob([ids.join('\n')], {type:'text/plain'});
  var a = document.createElement('a'); a.href = URL.createObjectURL(blob);
  a.download = 'rotection_discord_' + (currentScanData.id || 'export') + '.txt'; a.click();
}

function downloadDiscordJson() {
  if (!currentScanData) return;
  window.open(API_BASE + '/api/scans/' + currentScanData.id + '/discord-export', '_blank');
}
