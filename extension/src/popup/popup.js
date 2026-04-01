/**
 * Popup UI logic.
 *
 * On open: check auth → load config + clients → detect page context →
 * auto-match client → show capture interface.
 */

import { CONFIG } from '../utils/config.js';
import { isAuthenticated, signIn, signOut } from '../services/auth.js';
import {
  getExtensionConfig, getClients, captureContent, matchClient,
  getRecentCaptures, ERROR_CODES,
} from '../services/api.js';
import {
  captureTextSelection, captureFullPage, captureFileUrl,
  captureScreenshot, getPageMetadata,
} from '../services/capture.js';
import { getCachedClients, addRecentClientId, getRecentClientIds } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const authScreen = document.getElementById('auth-screen');
const mainScreen = document.getElementById('main-screen');
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const userEmail = document.getElementById('user-email');
const clientSelectHidden = document.getElementById('client-select');
const clientPickerBtn = document.getElementById('client-picker-btn');
const clientPickerText = document.getElementById('client-picker-text');
const autoMatchBadge = document.getElementById('auto-match-badge');
const clientDropdown = document.getElementById('client-dropdown');
const clientSearch = document.getElementById('client-search');
const clientListEl = document.getElementById('client-list');
const tagSelect = document.getElementById('tag-select');
const contentPreview = document.getElementById('content-preview');
const previewBody = document.getElementById('preview-body');
const captureBtn = document.getElementById('capture-btn');
const captureBtnText = document.getElementById('capture-btn-text');
const captureSpinner = document.getElementById('capture-spinner');
const captureCheck = document.getElementById('capture-check');
const statusEl = document.getElementById('status');
const usageSection = document.getElementById('usage-section');
const usageText = document.getElementById('usage-text');
const upgradeLink = document.getElementById('upgrade-link');
const progressBar = document.getElementById('progress-bar');
const recentSection = document.getElementById('recent-section');
const recentToggle = document.getElementById('recent-toggle');
const recentList = document.getElementById('recent-list');
const viewAllLink = document.getElementById('view-all-link');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let activeMode = 'text';
let activeTab = null;
let selectedText = '';
let extensionConfig = null;
let allClients = [];         // full client list
let recentClientIds = [];    // last 5 used client IDs
let autoMatchResult = null;  // { client_id, client_name, match_method, confidence }
let selectedClientId = '';
let parsedContent = null;    // { content, metadata, email_data, capture_type, document_tag }
const CLIENT_CACHE_TTL = 5 * 60 * 1000;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  const authed = await isAuthenticated();

  if (!authed) {
    showScreen('auth');
    return;
  }

  showScreen('main');

  // Populate document tag selector
  tagSelect.innerHTML = CONFIG.DOCUMENT_TAGS
    .map(t => `<option value="${t.value}">${t.label}</option>`)
    .join('');

  // Get active tab info
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    activeTab = tab;
  } catch { /* no tab access */ }

  // Check for pending capture from context menu
  let pendingCapture = null;
  try {
    const session = await chrome.storage.session.get('pending_capture');
    pendingCapture = session.pending_capture;
    if (pendingCapture && Date.now() - pendingCapture.timestamp < 30000) {
      setMode(pendingCapture.capture_type === 'text_selection' ? 'text' :
              pendingCapture.capture_type === 'full_page' ? 'page' :
              pendingCapture.capture_type === 'file_url' ? 'file' : 'page');
    } else {
      pendingCapture = null;
    }
    await chrome.storage.session.remove('pending_capture');
  } catch { /* no session storage */ }

  // Load recently used client IDs
  recentClientIds = await getRecentClientIds();

  // Load config + clients in parallel
  try {
    const [config, clients] = await Promise.all([
      loadConfig(),
      loadClients(),
    ]);

    extensionConfig = config;
    allClients = Array.isArray(clients) ? clients : [];
    renderClientList();
    updateUsage(config);

    // Auto-match if enabled (non-blocking UI — show shimmer while loading)
    if (config?.auto_match && activeTab?.url) {
      tryAutoMatch();
    }
  } catch (err) {
    handleApiError(err);
  }

  // Check for parsed content (Gmail emails, etc.)
  if (!pendingCapture && activeTab?.id) {
    await detectParsedContent();
  }

  // Detect selected text on the active page
  if (!pendingCapture && !parsedContent) {
    await detectSelectedText();
  } else if (pendingCapture?.capture_type === 'text_selection' && pendingCapture.data.text) {
    selectedText = pendingCapture.data.text;
    setMode('text');
  }

  updatePreview();

  // Load recent captures (non-blocking)
  loadRecentCaptures();
}

// ---------------------------------------------------------------------------
// Screen switching
// ---------------------------------------------------------------------------

function showScreen(screen) {
  authScreen.classList.toggle('hidden', screen !== 'auth');
  mainScreen.classList.toggle('hidden', screen !== 'main');
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadConfig() {
  return getExtensionConfig();
}

async function loadClients() {
  const cached = await getCachedClients();
  if (cached && cached._ts && Date.now() - cached._ts < CLIENT_CACHE_TTL) {
    return cached.clients;
  }
  return getClients();
}

// ---------------------------------------------------------------------------
// Client picker — custom searchable dropdown
// ---------------------------------------------------------------------------

function renderClientList(filter = '') {
  const query = filter.toLowerCase().trim();

  // Sort all clients alphabetically
  const sorted = [...allClients].sort((a, b) =>
    (a.name || '').localeCompare(b.name || ''));

  // Split into groups
  const recentSet = new Set(recentClientIds);
  const recentClients = recentClientIds
    .map(id => sorted.find(c => c.id === id))
    .filter(Boolean);
  const otherClients = sorted.filter(c => !recentSet.has(c.id));

  // Apply search filter
  const filterFn = (c) => {
    if (!query) return true;
    const name = (c.name || '').toLowerCase();
    const biz = (c.business_name || '').toLowerCase();
    return name.includes(query) || biz.includes(query);
  };

  let html = '';

  // Auto-match suggestion at top
  if (autoMatchResult && !query) {
    const mc = sorted.find(c => c.id === autoMatchResult.client_id);
    if (mc) {
      const conf = autoMatchResult.confidence || 'high';
      const method = autoMatchResult.match_method || 'match';
      html += `<div class="client-list-divider">Suggested match</div>`;
      html += clientOptionHtml(mc, true, conf, method);
    }
  }

  // Recently used
  const filteredRecent = recentClients.filter(filterFn);
  if (filteredRecent.length > 0) {
    html += `<div class="client-list-divider">Recently used</div>`;
    filteredRecent.slice(0, 3).forEach(c => {
      // Don't duplicate auto-match suggestion
      if (autoMatchResult?.client_id === c.id && !query) return;
      html += clientOptionHtml(c, false);
    });
  }

  // All clients
  const filteredOther = otherClients.filter(filterFn);
  const filteredAll = query
    ? sorted.filter(filterFn)
    : filteredOther;

  if (filteredAll.length > 0) {
    if (!query) html += `<div class="client-list-divider">All clients</div>`;
    filteredAll.forEach(c => {
      // Skip if already shown in auto-match or recent
      if (!query && autoMatchResult?.client_id === c.id) return;
      if (!query && recentSet.has(c.id)) return;
      html += clientOptionHtml(c, false);
    });
  }

  if (!html) {
    html = '<div class="client-list-empty">No clients found</div>';
  }

  clientListEl.innerHTML = html;

  // Attach click handlers
  clientListEl.querySelectorAll('.client-option').forEach(el => {
    el.addEventListener('click', () => {
      selectClient(el.dataset.id, el.dataset.name);
      closeDropdown();
    });
  });
}

function clientOptionHtml(client, isAutoMatch, confidence, method) {
  const selected = client.id === selectedClientId ? ' selected' : '';
  const matchClass = isAutoMatch ? ' auto-match-suggestion' : '';
  const label = escapeHtml(client.name || 'Unnamed');
  const biz = client.business_name ? `<span class="client-option-biz">${escapeHtml(client.business_name)}</span>` : '';
  const badge = isAutoMatch
    ? `<span class="match-badge ${confidence}">${escapeHtml(method)}</span>`
    : '';

  return `<div class="client-option${matchClass}${selected}" data-id="${client.id}" data-name="${escapeHtml(client.name || 'Unnamed')}">
    <span class="client-option-name">${label}</span>${biz}${badge}
  </div>`;
}

function selectClient(clientId, clientName) {
  selectedClientId = clientId;
  clientSelectHidden.value = clientId;

  // Update button text
  clientPickerText.textContent = clientName;
  clientPickerText.classList.remove('placeholder');

  // Show match badge in button if auto-matched
  if (autoMatchResult && autoMatchResult.client_id === clientId) {
    const conf = autoMatchResult.confidence || 'high';
    const method = autoMatchResult.match_method || 'match';
    autoMatchBadge.textContent = `Auto-matched via ${method}`;
    autoMatchBadge.className = `match-badge ${conf}`;
  } else {
    autoMatchBadge.classList.add('hidden');
  }

  // Highlight in list
  clientListEl.querySelectorAll('.client-option').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === clientId);
  });

  // Sync to session storage so sidepanel can pick it up
  chrome.storage.session.set({
    selected_client_id: clientId,
    selected_client_name: clientName,
  }).catch(() => {});

  updateCaptureButton();
}

// Dropdown open/close
clientPickerBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  const isOpen = clientDropdown.classList.contains('hidden');
  if (isOpen) openDropdown();
  else closeDropdown();
});

function openDropdown() {
  clientDropdown.classList.remove('hidden');
  clientPickerBtn.classList.add('open');
  clientSearch.value = '';
  renderClientList();
  // Focus search after a tick so the dropdown is visible
  setTimeout(() => clientSearch.focus(), 10);
}

function closeDropdown() {
  clientDropdown.classList.add('hidden');
  clientPickerBtn.classList.remove('open');
}

// Close on outside click
document.addEventListener('click', (e) => {
  if (!e.target.closest('#client-picker')) {
    closeDropdown();
  }
});

// Search filter
clientSearch.addEventListener('input', () => {
  renderClientList(clientSearch.value);
});

// Keyboard nav
clientSearch.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeDropdown();
    return;
  }
  if (e.key === 'Enter') {
    const first = clientListEl.querySelector('.client-option');
    if (first) {
      selectClient(first.dataset.id, first.dataset.name);
      closeDropdown();
    }
  }
});

// ---------------------------------------------------------------------------
// Auto-match
// ---------------------------------------------------------------------------

async function tryAutoMatch() {
  // Show loading state on picker
  clientPickerText.textContent = 'Finding matching client...';
  clientPickerText.classList.add('placeholder');
  clientPickerBtn.classList.add('loading');

  try {
    let pageData;
    try {
      pageData = await getPageMetadata(activeTab.id);
    } catch {
      pageData = {
        url: activeTab.url,
        domain: new URL(activeTab.url).hostname,
        title: activeTab.title || '',
        emails: [],
        companyNames: [],
      };
    }

    // Use richer match hints from parsed content (e.g., Gmail email addresses)
    const matchEmails = parsedContent?.metadata?.email_addresses || pageData.emails || [];
    const matchCompanies = parsedContent?.metadata?.company_names || pageData.companyNames || [];

    const result = await matchClient({
      url: pageData.url || activeTab.url,
      email_addresses: matchEmails,
      company_names: matchCompanies,
      page_title: pageData.title || activeTab.title || '',
    });

    if (result?.matched && result.client_id) {
      autoMatchResult = result;
      // Sync auto-match to session storage for sidepanel
      chrome.storage.session.set({ auto_match_result: result }).catch(() => {});
      renderClientList();
      selectClient(result.client_id, result.client_name || getClientName(result.client_id));
    } else {
      // No match — reset to placeholder
      resetPickerText();
    }
  } catch {
    // Auto-match failed silently — just reset
    resetPickerText();
  }

  clientPickerBtn.classList.remove('loading');
}

function getClientName(id) {
  const c = allClients.find(cl => cl.id === id);
  return c?.name || 'Unknown';
}

function resetPickerText() {
  if (!selectedClientId) {
    clientPickerText.textContent = 'Select a client...';
    clientPickerText.classList.add('placeholder');
  }
}

// ---------------------------------------------------------------------------
// Detect selected text
// ---------------------------------------------------------------------------

async function detectSelectedText() {
  if (!activeTab?.id) return;
  try {
    const response = await chrome.tabs.sendMessage(activeTab.id, { type: 'GET_SELECTED_TEXT' });
    const text = response?.text?.trim();
    if (text && text.length > 0) {
      selectedText = text;
      setMode('text');
    } else {
      setMode('page');
    }
  } catch {
    setMode('page');
  }
}

// ---------------------------------------------------------------------------
// Parsed content detection (Gmail emails, etc.)
// ---------------------------------------------------------------------------

async function detectParsedContent() {
  if (!activeTab?.id) return;
  try {
    const response = await chrome.tabs.sendMessage(activeTab.id, { type: 'GET_PARSED_CONTENT' });
    if (!response?.parsed) return;

    parsedContent = response;

    // Auto-set document tag
    if (response.document_tag) {
      const option = tagSelect.querySelector(`option[value="${response.document_tag}"]`);
      if (option) tagSelect.value = response.document_tag;
    }

    // Set capture mode from parser
    if (response.capture_type === 'text_selection') {
      setMode('text');
    }

    // Show detection badge near capture tabs
    showParserBadge(response.email_data);

    // Update preview with email summary
    updatePreview();
  } catch { /* content script not available */ }
}

function showParserBadge(emailData) {
  // Remove existing badge if any
  const existing = document.getElementById('parser-badge');
  if (existing) existing.remove();

  const badge = document.createElement('div');
  badge.id = 'parser-badge';
  badge.className = 'parser-badge';
  badge.innerHTML = `<span class="parser-badge-icon">\u{1F4E7}</span> Gmail email detected`;

  // Insert after capture tabs
  const tabsEl = document.querySelector('.capture-tabs');
  if (tabsEl) {
    tabsEl.parentNode.insertBefore(badge, tabsEl.nextSibling);
  }
}

// ---------------------------------------------------------------------------
// Recent captures list
// ---------------------------------------------------------------------------

async function loadRecentCaptures() {
  try {
    const captures = await getRecentCaptures();
    const items = Array.isArray(captures) ? captures : (captures?.captures || []);
    if (items.length === 0) return;

    const recent = items.slice(0, 3);
    recentList.innerHTML = recent.map(c => {
      const domain = c.source_url ? extractDomain(c.source_url) : '';
      const time = c.created_at ? formatRelativeTime(c.created_at) : '';
      return `<div class="recent-item">
        <span class="recent-client">${escapeHtml(c.client_name || 'Unknown')}</span>
        <div class="recent-meta">
          ${domain ? `<span class="recent-url">${escapeHtml(domain)}</span>` : ''}
          ${time ? `<span>${time}</span>` : ''}
        </div>
      </div>`;
    }).join('');

    recentSection.classList.remove('hidden');
    viewAllLink.classList.remove('hidden');
  } catch {
    // Non-critical
  }
}

// ---------------------------------------------------------------------------
// Capture mode tabs
// ---------------------------------------------------------------------------

document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    setMode(tab.dataset.mode);
    updatePreview();
  });
});

function setMode(mode) {
  activeMode = mode;
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.mode === mode);
  });
}

// ---------------------------------------------------------------------------
// Content preview
// ---------------------------------------------------------------------------

function updatePreview() {
  contentPreview.classList.remove('hidden');

  switch (activeMode) {
    case 'text':
      if (parsedContent?.email_data) {
        const ed = parsedContent.email_data;
        const fromLine = ed.from_name || ed.from_email || 'Unknown sender';
        const subjectLine = ed.subject || 'No subject';
        const threadInfo = ed.thread_length > 1 ? ` (${ed.thread_length} messages)` : '';
        previewBody.innerHTML =
          `<span class="preview-title">${escapeHtml(`Email from ${fromLine}`)}</span>` +
          `<span class="preview-url">${escapeHtml(subjectLine)}${threadInfo}</span>`;
      } else if (selectedText) {
        const truncated = selectedText.length > 200
          ? selectedText.slice(0, 200) + '...'
          : selectedText;
        previewBody.innerHTML = escapeHtml(truncated);
      } else {
        previewBody.innerHTML = '<span class="preview-placeholder">Select text on the page, then capture</span>';
      }
      break;

    case 'page':
      if (activeTab) {
        previewBody.innerHTML =
          `<span class="preview-title">${escapeHtml(activeTab.title || 'Untitled')}</span>` +
          `<span class="preview-url">${escapeHtml(activeTab.url || '')}</span>`;
      } else {
        previewBody.innerHTML = '<span class="preview-placeholder">No page detected</span>';
      }
      break;

    case 'file':
      previewBody.innerHTML = '<span class="preview-placeholder">Right-click a link and choose "Capture linked file"</span>';
      break;

    case 'screenshot':
      previewBody.innerHTML = '<span class="preview-placeholder">Click capture to screenshot the visible page</span>';
      break;

    default:
      contentPreview.classList.add('hidden');
  }
}

// ---------------------------------------------------------------------------
// Capture button state
// ---------------------------------------------------------------------------

function updateCaptureButton() {
  if (!selectedClientId) {
    captureBtn.disabled = true;
    captureBtnText.textContent = 'Select a client to capture';
    return;
  }

  const clientName = getClientName(selectedClientId);
  captureBtn.disabled = false;
  captureBtnText.textContent = `Capture to ${clientName}`;
}

// ---------------------------------------------------------------------------
// Capture flow
// ---------------------------------------------------------------------------

captureBtn.addEventListener('click', handleCapture);

async function handleCapture() {
  if (!selectedClientId) {
    showStatus('Please select a client first.', 'error');
    return;
  }

  const clientId = selectedClientId;
  const tag = tagSelect.value;
  setBtnLoading(true);
  hideStatus();

  try {
    if (!activeTab?.id) {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      activeTab = tab;
    }

    const tabId = activeTab?.id;
    let payload;

    switch (activeMode) {
      case 'text':
        // Use parsed content (e.g., Gmail email) if available
        if (parsedContent?.content) {
          payload = { type: 'text_selection', content: parsedContent.content };
        } else {
          payload = await captureTextSelection(tabId);
        }
        break;

      case 'page':
        payload = await captureFullPage(tabId);
        break;

      case 'file': {
        const session = await chrome.storage.session.get('pending_capture');
        const pending = session?.pending_capture;
        if (!pending?.data?.fileUrl) {
          showStatus('No file link captured. Right-click a link to capture.', 'error');
          setBtnLoading(false);
          return;
        }
        payload = await captureFileUrl(pending.data.fileUrl);
        break;
      }

      case 'screenshot':
        payload = await captureScreenshot(tabId);
        break;
    }

    const metadata = {
      url: activeTab?.url || '',
      page_title: activeTab?.title || '',
      captured_at: new Date().toISOString(),
      site_domain: activeTab?.url ? extractDomain(activeTab.url) : '',
    };

    const capturePayload = payload.type === 'file_url'
      ? payload.file_url
      : (payload.image_data || payload.content || '');

    const result = await captureContent(clientId, payload.type, capturePayload, metadata, tag);

    // Track recently used client
    await addRecentClientId(clientId);

    // Success animation
    setBtnLoading(false);
    showBtnSuccess();

    // Update badge
    chrome.runtime.sendMessage({ type: 'CAPTURE_COMPLETE' }).catch(() => {});

    // Refresh usage
    if (extensionConfig) {
      extensionConfig.captures_today = (extensionConfig.captures_today || 0) + 1;
      if (extensionConfig.captures_per_day > 0) {
        extensionConfig.captures_remaining = Math.max(0,
          (extensionConfig.captures_remaining || 0) - 1);
      }
      updateUsage(extensionConfig);
    }

    if (result?.warning) {
      showStatus(result.warning, 'success');
    }
    setTimeout(() => window.close(), 2000);

  } catch (err) {
    setBtnLoading(false);
    handleApiError(err);
  }
}

// ---------------------------------------------------------------------------
// Button states
// ---------------------------------------------------------------------------

function setBtnLoading(loading) {
  captureBtn.disabled = loading;
  captureBtnText.classList.toggle('hidden', loading);
  captureSpinner.classList.toggle('hidden', !loading);
  captureCheck.classList.add('hidden');

  document.querySelectorAll('.tab, .select').forEach(el => {
    el.disabled = loading;
    if (loading) el.style.pointerEvents = 'none';
    else el.style.pointerEvents = '';
  });

  // Disable client picker during capture
  clientPickerBtn.disabled = loading;
}

function showBtnSuccess() {
  captureBtn.classList.add('btn-success');
  captureBtnText.classList.add('hidden');
  captureSpinner.classList.add('hidden');
  captureCheck.classList.remove('hidden');
}

// ---------------------------------------------------------------------------
// Usage display
// ---------------------------------------------------------------------------

function updateUsage(config) {
  if (!config || config.captures_per_day === -1) {
    usageSection.classList.remove('hidden');
    usageText.textContent = `${config.captures_today || 0} captures today (unlimited)`;
    progressBar.style.width = '0%';
    upgradeLink.classList.add('hidden');
    return;
  }

  if (config.captures_per_day > 0) {
    usageSection.classList.remove('hidden');
    const used = config.captures_today || 0;
    const total = config.captures_per_day;
    const remaining = config.captures_remaining ?? (total - used);
    const pct = Math.min(100, (used / total) * 100);

    usageText.textContent = `${used} of ${total} captures today`;
    progressBar.style.width = `${pct}%`;

    if (remaining <= 0) {
      progressBar.classList.add('limit-reached');
      upgradeLink.classList.remove('hidden');
      captureBtn.disabled = true;
      captureBtnText.textContent = 'Daily limit reached';
    } else {
      progressBar.classList.remove('limit-reached');
      upgradeLink.classList.add('hidden');
    }
  }
}

// ---------------------------------------------------------------------------
// Status messages
// ---------------------------------------------------------------------------

function showStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
  statusEl.classList.remove('hidden');

  if (type === 'success') {
    setTimeout(() => statusEl.classList.add('hidden'), 4000);
  }
}

function hideStatus() {
  statusEl.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Error handling
// ---------------------------------------------------------------------------

function handleApiError(err) {
  if (err.code === ERROR_CODES.AUTH_EXPIRED) {
    showScreen('auth');
    return;
  }
  if (err.code === ERROR_CODES.TIER_UPGRADE) {
    showStatus('This feature requires a paid plan.', 'error');
    if (err.upgradeUrl) {
      upgradeLink.href = err.upgradeUrl;
      upgradeLink.classList.remove('hidden');
    }
    return;
  }
  if (err.code === ERROR_CODES.RATE_LIMITED) {
    showStatus(err.message || 'Daily capture limit reached.', 'error');
    return;
  }
  showStatus(err.message || 'Something went wrong.', 'error');
}

// ---------------------------------------------------------------------------
// Recent captures toggle
// ---------------------------------------------------------------------------

recentToggle.addEventListener('click', () => {
  const isOpen = recentToggle.classList.toggle('open');
  recentList.classList.toggle('hidden', !isOpen);
  viewAllLink.classList.toggle('hidden', !isOpen);
});

// ---------------------------------------------------------------------------
// Auth events
// ---------------------------------------------------------------------------

signInBtn.addEventListener('click', () => signIn());

signOutBtn.addEventListener('click', async () => {
  await signOut();
  showScreen('auth');
});

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'AUTH_STATE_CHANGED' && message.authenticated) {
    init();
  }
  if (message.type === 'TAB_CHANGED') {
    // Active tab changed — clear auto-match and re-detect
    autoMatchResult = null;
    selectedText = '';
    chrome.storage.session.remove('auto_match_result').catch(() => {});
    if (extensionConfig?.auto_match && message.tab?.url) {
      activeTab = message.tab;
      tryAutoMatch();
    } else {
      resetPickerText();
    }
    updatePreview();
  }
});

// Sync state from sidepanel changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'session') return;

  if (changes.selected_client_id && changes.selected_client_id.newValue) {
    const id = changes.selected_client_id.newValue;
    const name = changes.selected_client_name?.newValue || getClientName(id);
    if (id !== selectedClientId) {
      selectedClientId = id;
      clientSelectHidden.value = id;
      clientPickerText.textContent = name;
      clientPickerText.classList.remove('placeholder');
      clientListEl.querySelectorAll('.client-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === id);
      });
      updateCaptureButton();
    }
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function extractDomain(url) {
  try { return new URL(url).hostname; } catch { return ''; }
}

function formatRelativeTime(dateStr) {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diffMin = Math.floor((now - then) / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

init();
