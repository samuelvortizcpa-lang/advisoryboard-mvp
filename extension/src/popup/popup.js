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
import { getCachedClients } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const authScreen = document.getElementById('auth-screen');
const mainScreen = document.getElementById('main-screen');
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const userEmail = document.getElementById('user-email');
const clientSelect = document.getElementById('client-select');
const autoMatchBadge = document.getElementById('auto-match-badge');
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
const CLIENT_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

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
      // Use the pending capture's mode
      setMode(pendingCapture.capture_type === 'text_selection' ? 'text' :
              pendingCapture.capture_type === 'full_page' ? 'page' :
              pendingCapture.capture_type === 'file_url' ? 'file' : 'page');
    } else {
      pendingCapture = null;
    }
    await chrome.storage.session.remove('pending_capture');
  } catch { /* no session storage */ }

  // Load config + clients in parallel
  try {
    const [config, clients] = await Promise.all([
      loadConfig(),
      loadClients(),
    ]);

    extensionConfig = config;
    populateClients(clients);
    updateUsage(config);

    // Auto-match client if enabled
    if (config?.auto_match && activeTab?.url) {
      await tryAutoMatch();
    }
  } catch (err) {
    handleApiError(err);
  }

  // Detect selected text on the active page
  if (!pendingCapture) {
    await detectSelectedText();
  } else if (pendingCapture.capture_type === 'text_selection' && pendingCapture.data.text) {
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
  const config = await getExtensionConfig();
  return config;
}

async function loadClients() {
  // Use cache if fresh enough
  const cached = await getCachedClients();
  if (cached && cached._ts && Date.now() - cached._ts < CLIENT_CACHE_TTL) {
    return cached.clients;
  }

  const clients = await getClients();
  return clients;
}

function populateClients(clients) {
  if (!Array.isArray(clients)) return;

  clientSelect.innerHTML = '<option value="">Select a client...</option>' +
    clients.map(c => {
      const label = c.business_name ? `${c.name} — ${c.business_name}` : c.name;
      return `<option value="${c.id}">${escapeHtml(label)}</option>`;
    }).join('');
}

async function tryAutoMatch() {
  try {
    // Get page metadata from content script
    let pageData;
    try {
      pageData = await chrome.tabs.sendMessage(activeTab.id, { type: 'GET_PAGE_METADATA' });
    } catch {
      pageData = {
        url: activeTab.url,
        domain: new URL(activeTab.url).hostname,
        page_text_snippet: activeTab.title || '',
      };
    }

    const result = await matchClient({
      url: pageData.url || activeTab.url,
      email_addresses: pageData.email_addresses || [],
      company_names: [],
      page_title: activeTab.title || '',
    });

    if (result?.matched && result.client_id) {
      clientSelect.value = result.client_id;
      autoMatchBadge.classList.remove('hidden');
      updateCaptureButton();
    }
  } catch {
    // Auto-match is best-effort
  }
}

async function detectSelectedText() {
  if (!activeTab?.id) return;
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: () => window.getSelection().toString(),
    });
    const text = result?.result?.trim();
    if (text && text.length > 0) {
      selectedText = text;
      setMode('text');
    } else {
      setMode('page');
    }
  } catch {
    // Can't access page (chrome:// URLs, etc.)
    setMode('page');
  }
}

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
    // Recent captures are non-critical
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
      if (selectedText) {
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

clientSelect.addEventListener('change', () => {
  autoMatchBadge.classList.add('hidden');
  updateCaptureButton();
});

function updateCaptureButton() {
  const clientId = clientSelect.value;
  if (!clientId) {
    captureBtn.disabled = true;
    captureBtnText.textContent = 'Select a client to capture';
    return;
  }

  const clientName = clientSelect.options[clientSelect.selectedIndex].text;
  captureBtn.disabled = false;
  captureBtnText.textContent = `Capture to ${clientName}`;
}

// ---------------------------------------------------------------------------
// Capture flow
// ---------------------------------------------------------------------------

captureBtn.addEventListener('click', handleCapture);

async function handleCapture() {
  const clientId = clientSelect.value;
  if (!clientId) {
    showStatus('Please select a client first.', 'error');
    return;
  }

  const tag = tagSelect.value;
  setBtnLoading(true);
  hideStatus();

  try {
    if (!activeTab?.id) {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      activeTab = tab;
    }

    let content = '';
    let captureType = '';
    let metadata = {
      url: activeTab?.url || '',
      page_title: activeTab?.title || '',
      captured_at: new Date().toISOString(),
      site_domain: activeTab?.url ? extractDomain(activeTab.url) : '',
    };

    switch (activeMode) {
      case 'text': {
        // Get fresh selection
        let text = selectedText;
        if (activeTab?.id) {
          try {
            const [result] = await chrome.scripting.executeScript({
              target: { tabId: activeTab.id },
              func: () => window.getSelection().toString(),
            });
            if (result?.result?.trim()) text = result.result.trim();
          } catch { /* use cached */ }
        }
        if (!text) {
          showStatus('No text selected on the page.', 'error');
          setBtnLoading(false);
          return;
        }
        captureType = 'text_selection';
        content = text.slice(0, CONFIG.MAX_TEXT_LENGTH);
        break;
      }

      case 'page': {
        if (!activeTab?.id) {
          showStatus('Cannot access the current page.', 'error');
          setBtnLoading(false);
          return;
        }
        const [result] = await chrome.scripting.executeScript({
          target: { tabId: activeTab.id },
          func: () => document.body?.innerText || '',
        });
        const pageText = result?.result?.trim();
        if (!pageText) {
          showStatus('Page has no text content.', 'error');
          setBtnLoading(false);
          return;
        }
        captureType = 'full_page';
        content = pageText.slice(0, CONFIG.MAX_TEXT_LENGTH);
        break;
      }

      case 'file': {
        // File URL comes from context menu pending capture
        const session = await chrome.storage.session.get('pending_capture');
        const pending = session?.pending_capture;
        if (pending?.data?.fileUrl) {
          captureType = 'file_url';
          content = pending.data.fileUrl;
        } else {
          showStatus('No file link captured. Right-click a link to capture.', 'error');
          setBtnLoading(false);
          return;
        }
        break;
      }

      case 'screenshot': {
        const dataUrl = await chrome.tabs.captureVisibleTab(null, {
          format: 'png',
          quality: 90,
        });
        captureType = 'screenshot';
        content = dataUrl.split(',')[1]; // base64
        break;
      }
    }

    const result = await captureContent(clientId, captureType, content, metadata, tag);

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

    // Show success, auto-close after 2s
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

  // Disable all tabs and selectors during capture
  document.querySelectorAll('.tab, .select').forEach(el => {
    el.disabled = loading;
    if (loading) el.style.pointerEvents = 'none';
    else el.style.pointerEvents = '';
  });
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
    // Unlimited tier
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

// Listen for auth state changes from the service worker
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'AUTH_STATE_CHANGED' && message.authenticated) {
    init();
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
