// Globals, constants, and utility functions

var API_BASE = '';
var currentUser = null;
var currentScanData = null;
var currentScanStatuses = {};
var allUsers = [];
var filteredUsers = [];
var sortCol = 'name';
var sortDir = 1;
var currentPage = 1;
var perPage = 100;
var discordFormat = 'space';
var groupChartInstance = null;
var flagChartInstance = null;
var confChartInstance = null;
var _pendingQueueId = null;

var FLAG_MAP = {
  0:{name:'Unflagged',color:'#6b7280'}, 1:{name:'Flagged',color:'#ef4444'},
  2:{name:'Confirmed',color:'#dc2626'}, 3:{name:'Queued',color:'#f59e0b'},
  5:{name:'Mixed',color:'#f97316'}, 6:{name:'Past Offender',color:'#8b5cf6'}
};

var STATUS_CSS = {
  'SEA Banned':'ust-sea-banned','False Positive':'ust-false-positive',
  'Suspicious':'ust-suspicious','Under Investigation':'ust-under-investigation',
  'Pending Review':'ust-pending-review'
};

var ALL_STATUSES = ['Pending Review','SEA Banned','False Positive','Suspicious','Under Investigation'];
var ROLE_OPTIONS = ['SEA Moderator','Division Administrator','Division Leader','Moderator at a division','Individual','Other'];

var SEA_GROUP_ID = 2648601;

var SAFE_THUMB_PREFIX = 'https://tr.rbxcdn.com/';

function safeThumbnail(url) { if (!url) return ''; return url.startsWith(SAFE_THUMB_PREFIX) ? esc(url) : ''; }
function safeDiscordId(id) { return /^\d+$/.test(id) ? id : esc(id); }
function esc(s) { var d = document.createElement('div'); d.textContent = s||''; return d.innerHTML; }

function canSetStatus() {
  if (!currentUser) return false;
  if (currentUser.is_admin) return true;
  if (currentUser.roles.includes('Division Administrator') && currentUser.admin_confirmed) return true;
  if (currentUser.roles.includes('SEA Moderator')) return true;
  return false;
}
function canSeeInternalStatuses() { return canSetStatus(); }
function isAdmin() { return currentUser && currentUser.is_admin; }

function fmtEta(seconds) {
  if (seconds == null || seconds <= 0) return '—';
  if (seconds < 60) return Math.round(seconds) + 's';
  if (seconds < 3600) return Math.round(seconds / 60) + 'm ' + Math.round(seconds % 60) + 's';
  var h = Math.floor(seconds / 3600), m = Math.round((seconds % 3600) / 60);
  return h + 'h ' + m + 'm';
}
