// Discord Export with Advanced Filtering

let discordFilters = {
  minConfidence: 0,
  excludeSeabanned: false,
  excludeFalsePositives: true
};

function renderDiscordPanel() {
  if (!currentScanData) return;
  var ids = currentScanData.discord_ids || [];
  document.getElementById('discordIdCount').textContent = ids.length;
  updateDiscordBox();
  renderDiscordFilters();
}

function renderDiscordFilters() {
  var filterHtml = `
    <div class="discord-filters" style="margin-bottom: 16px; padding: 16px; background: var(--bg3); border: 1px solid var(--border); border-radius: 8px;">
      <h4 style="margin-bottom: 12px; font-size: 13px; font-weight: 600; text-transform: uppercase; color: var(--text2);">Filter Options</h4>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <label style="font-size: 12px; color: var(--text2);">Min Confidence:</label>
          <input type="range" id="minConfidenceSlider" min="0" max="1" step="0.1" value="${discordFilters.minConfidence}" 
            onchange="updateDiscordFilters()" style="flex: 1; accent-color: var(--accent);">
          <span id="minConfidenceValue" style="font-size: 12px; min-width: 30px;">${(discordFilters.minConfidence * 100).toFixed(0)}%</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="excludeSeabanCheck" ${discordFilters.excludeSeabanned ? 'checked' : ''} 
            onchange="updateDiscordFilters()" style="accent-color: var(--accent);">
          <label for="excludeSeabanCheck" style="font-size: 12px; color: var(--text2); cursor: pointer;">Exclude SEA Banned</label>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="excludeFalsePositiveCheck" ${discordFilters.excludeFalsePositives ? 'checked' : ''} 
            onchange="updateDiscordFilters()" style="accent-color: var(--accent);">
          <label for="excludeFalsePositiveCheck" style="font-size: 12px; color: var(--text2); cursor: pointer;">Exclude False Positives</label>
        </div>
      </div>
      <button class="btn btn-secondary btn-sm" style="margin-top: 12px; width: 100%;" onclick="applyDiscordFilters()">Apply Filters & Reload</button>
    </div>
  `;
  
  var filterContainer = document.querySelector('.export-options');
  if (filterContainer) {
    filterContainer.insertAdjacentHTML('afterend', filterHtml);
  }
}

function updateDiscordFilters() {
  var slider = document.getElementById('minConfidenceSlider');
  var seabannCheck = document.getElementById('excludeSeabanCheck');
  var falsePositiveCheck = document.getElementById('excludeFalsePositiveCheck');
  
  if (slider) discordFilters.minConfidence = parseFloat(slider.value);
  if (seabannCheck) discordFilters.excludeSeabanned = seabannCheck.checked;
  if (falsePositiveCheck) discordFilters.excludeFalsePositives = falsePositiveCheck.checked;
  
  var valueSpan = document.getElementById('minConfidenceValue');
  if (valueSpan) valueSpan.textContent = (discordFilters.minConfidence * 100).toFixed(0) + '%';
}

function applyDiscordFilters() {
  if (!currentScanData) return;
  
  var url = API_BASE + '/api/scans/' + currentScanData.id + '/discord-export?' +
    'min_confidence=' + discordFilters.minConfidence +
    '&exclude_seabanned=' + (discordFilters.excludeSeabanned ? 'true' : 'false') +
    '&exclude_false_positives=' + (discordFilters.excludeFalsePositives ? 'true' : 'false');
  
  fetch(url)
    .then(r => r.json())
    .then(data => {
      currentScanData.discord_ids = data.discord_ids;
      document.getElementById('discordIdCount').textContent = data.discord_ids.length;
      updateDiscordBox();
      showNotification('Filters applied! ' + data.discord_ids.length + ' Discord IDs after filtering.', 'success');
    })
    .catch(e => showNotification('Error applying filters: ' + e.message, 'error'));
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
  var url = API_BASE + '/api/scans/' + currentScanData.id + '/discord-export?' +
    'min_confidence=' + discordFilters.minConfidence +
    '&exclude_seabanned=' + (discordFilters.excludeSeabanned ? 'true' : 'false') +
    '&exclude_false_positives=' + (discordFilters.excludeFalsePositives ? 'true' : 'false');
  window.open(url, '_blank');
}
