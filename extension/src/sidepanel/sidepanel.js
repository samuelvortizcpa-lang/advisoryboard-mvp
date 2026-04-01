/**
 * Side panel — primary extension UI.
 *
 * Three tabs: Capture | Chat | Rules
 *
 * On open: check auth → load config + clients → detect page context →
 * auto-match client → show capture interface.
 */

import { CONFIG } from '../utils/config.js';
import { getToken, signIn, signOut } from '../services/auth.js';
import {
  getExtensionConfig, getClients, captureContent, matchClient,
  getRecentCaptures, getMonitoringRules, createMonitoringRule,
  updateMonitoringRule, deleteMonitoringRule, askQuestion, ERROR_CODES,
} from '../services/api.js';
import { captureFileUrl, getPageMetadata } from '../services/capture.js';
import { getCachedClients, addRecentClientId, getRecentClientIds } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// DOM refs — shared
// ---------------------------------------------------------------------------

const authScreen = document.getElementById('auth-screen');
const mainScreen = document.getElementById('main-screen');
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const userEmail = document.getElementById('user-email');
const monitoringToggle = document.getElementById('monitoring-toggle');

// ---------------------------------------------------------------------------
// DOM refs — capture panel
// ---------------------------------------------------------------------------

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
const usageFooter = document.getElementById('usage-footer');
const footerUsageText = document.getElementById('footer-usage-text');
const footerTierBadge = document.getElementById('footer-tier-badge');
const footerProgressTrack = document.getElementById('footer-progress-track');
const footerProgressBar = document.getElementById('footer-progress-bar');
const footerUpgrade = document.getElementById('footer-upgrade');
const parserBadgeBar = document.getElementById('parser-badge-bar');
const recentSection = document.getElementById('recent-section');
const recentToggleBtn = document.getElementById('recent-toggle');
const recentListEl = document.getElementById('recent-list');
const recentRefreshBtn = document.getElementById('recent-refresh');
const quickRuleLink = document.getElementById('quick-rule-link');
const createRuleFromMatch = document.getElementById('create-rule-from-match');

// ---------------------------------------------------------------------------
// DOM refs — chat panel
// ---------------------------------------------------------------------------

const chatTierGate = document.getElementById('chat-tier-gate');
const chatArea = document.getElementById('chat-area');
const chatClientBtn = document.getElementById('chat-client-btn');
const chatClientText = document.getElementById('chat-client-text');
const chatClientDropdown = document.getElementById('chat-client-dropdown');
const chatClientSearch = document.getElementById('chat-client-search');
const chatClientList = document.getElementById('chat-client-list');
const chatMessages = document.getElementById('chat-messages');
const contextBanner = document.getElementById('context-banner');
const insertContextBtn = document.getElementById('insert-context-btn');
const dismissContextBtn = document.getElementById('dismiss-context-btn');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const throttleMsg = document.getElementById('throttle-msg');

// ---------------------------------------------------------------------------
// DOM refs — rules panel
// ---------------------------------------------------------------------------

const rulesListEl = document.getElementById('rules-list');
const rulesForm = document.getElementById('rules-form');
const rulesFormCancel = document.getElementById('rules-form-cancel');
const ruleNameInput = document.getElementById('rule-name');
const ruleTypeSelect = document.getElementById('rule-type');
const rulePatternInput = document.getElementById('rule-pattern');
const ruleClientSelect = document.getElementById('rule-client');
const ruleSaveBtn = document.getElementById('rule-save-btn');
const ruleSaveText = document.getElementById('rule-save-text');
const ruleSaveSpinner = document.getElementById('rule-save-spinner');
const addRuleBtn = document.getElementById('add-rule-btn');
const rulesAddSection = document.getElementById('rules-add-section');
const rulesGate = document.getElementById('rules-gate');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let activeMode = 'text';
let activeTab = null;
let selectedText = '';
let extensionConfig = null;
let allClients = [];
let recentClientIds = [];
let autoMatchResult = null;
let selectedClientId = '';
let parsedContent = null;
let monitoringRules = [];
let activePanel = 'capture';
const CLIENT_CACHE_TTL = 5 * 60 * 1000;

// Parser badge state
let dismissedBadgeTabId = null; // tab ID where user dismissed the badge

// Chat-specific state
let chatSelectedClientId = '';
let chatSelectedClientName = '';
let chatHistory = [];
const queryTimestamps = [];

// Monitoring
let monitoringPrefs = { enabled: true, muted_until: 0 };

// ---------------------------------------------------------------------------
// Tab detection — side panels don't always share window context
// ---------------------------------------------------------------------------

async function getActiveTab() {
  try {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const good = tabs?.find(t => t.url && !t.url.startsWith('chrome://') && !t.url.startsWith('chrome-extension://'));
    if (good) return good;
  } catch { /* fall through */ }

  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const good = tabs?.find(t => t.url && !t.url.startsWith('chrome://') && !t.url.startsWith('chrome-extension://'));
    if (good) return good;
  } catch { /* fall through */ }

  try {
    const tabs = await chrome.tabs.query({ active: true });
    for (const tab of tabs) {
      if (tab.url && !tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
        return tab;
      }
    }
  } catch { /* fall through */ }

  return null;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  // Wait for the auth token to be available in storage before doing anything.
  // This avoids firing API calls that will 401 because the token hasn't been
  // written yet (e.g. service worker just stored it via AUTH_TOKEN_FROM_PAGE).
  const token = await getToken();

  if (!token) {
    showScreen('auth');
    return;
  }

  showScreen('main');

  // Populate document tag selector — default to "other"
  tagSelect.innerHTML = CONFIG.DOCUMENT_TAGS
    .map(t => `<option value="${t.value}">${t.label}</option>`)
    .join('');
  tagSelect.value = 'other';

  // Get active tab info
  activeTab = await getActiveTab();

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
    renderChatClientList();
    updateUsage(config);
    updateFooterUsage(config);

    // Load recent captures (non-blocking)
    loadRecentCaptures().catch(() => {});

    // Set up chat availability
    if (!config.quick_query) {
      chatTierGate.classList.remove('hidden');
      chatArea.classList.add('hidden');
    }

    // Auto-match if enabled
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

  // Initialize monitoring toggle
  initMonitoringToggle();

  // Check for pre-selected client from storage
  try {
    const session = await chrome.storage.session.get(['selected_client_id', 'selected_client_name']);
    if (session.selected_client_id) {
      const id = session.selected_client_id;
      const name = session.selected_client_name || getClientName(id);
      if (allClients.some(c => c.id === id)) {
        selectClient(id, name);
        selectChatClient(id, name);
      }
    }
  } catch { /* no pre-selection */ }

  // Check for selected text for chat context
  await checkSelectedTextForChat();

  // Check for pre-filled query text from context menu
  try {
    const session = await chrome.storage.session.get('sidepanel_query');
    if (session.sidepanel_query) {
      queryInput.value = session.sidepanel_query;
      autoResizeInput();
      await chrome.storage.session.remove('sidepanel_query');
      // Auto-switch to chat tab
      switchPanel('chat');
    }
  } catch { /* no pre-fill */ }
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
// Main tab switching (Capture / Chat / Rules)
// ---------------------------------------------------------------------------

document.querySelectorAll('.main-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    switchPanel(tab.dataset.panel);
  });
});

function switchPanel(panel) {
  activePanel = panel;

  document.querySelectorAll('.main-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.panel === panel);
  });

  document.getElementById('panel-capture').classList.toggle('hidden', panel !== 'capture');
  document.getElementById('panel-chat').classList.toggle('hidden', panel !== 'chat');
  document.getElementById('panel-rules').classList.toggle('hidden', panel !== 'rules');

  // Load data on first visit
  if (panel === 'rules') loadRules();
}

// ===========================================================================
// CAPTURE PANEL
// ===========================================================================

// ---------------------------------------------------------------------------
// Client picker — custom searchable dropdown
// ---------------------------------------------------------------------------

function renderClientList(filter = '') {
  const query = filter.toLowerCase().trim();
  const sorted = [...allClients].sort((a, b) =>
    (a.name || '').localeCompare(b.name || ''));

  const recentSet = new Set(recentClientIds);
  const recentClients = recentClientIds
    .map(id => sorted.find(c => c.id === id))
    .filter(Boolean);
  const otherClients = sorted.filter(c => !recentSet.has(c.id));

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
      html += '<div class="client-list-divider">Suggested match</div>';
      html += clientOptionHtml(mc, true, conf, method);
    }
  }

  // Recently used
  const filteredRecent = recentClients.filter(filterFn);
  if (filteredRecent.length > 0) {
    html += '<div class="client-list-divider">Recently used</div>';
    filteredRecent.slice(0, 3).forEach(c => {
      if (autoMatchResult?.client_id === c.id && !query) return;
      html += clientOptionHtml(c, false);
    });
  }

  // All clients
  const filteredOther = otherClients.filter(filterFn);
  const filteredAll = query ? sorted.filter(filterFn) : filteredOther;

  if (filteredAll.length > 0) {
    if (!query) html += '<div class="client-list-divider">All clients</div>';
    filteredAll.forEach(c => {
      if (!query && autoMatchResult?.client_id === c.id) return;
      if (!query && recentSet.has(c.id)) return;
      html += clientOptionHtml(c, false);
    });
  }

  if (!html) {
    html = '<div class="client-list-empty">No clients found</div>';
  }

  clientListEl.innerHTML = html;

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

  clientPickerText.textContent = clientName;
  clientPickerText.classList.remove('placeholder');

  // Show match badge if auto-matched
  if (autoMatchResult && autoMatchResult.client_id === clientId) {
    const conf = autoMatchResult.confidence || 'high';
    const method = autoMatchResult.match_method || 'match';
    autoMatchBadge.textContent = `Auto-matched via ${method}`;
    autoMatchBadge.className = `match-badge ${conf}`;
    quickRuleLink.classList.remove('hidden');
  } else {
    autoMatchBadge.classList.add('hidden');
    quickRuleLink.classList.add('hidden');
  }

  // Highlight in list
  clientListEl.querySelectorAll('.client-option').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === clientId);
  });

  // Sync to session storage
  chrome.storage.session.set({
    selected_client_id: clientId,
    selected_client_name: clientName,
  }).catch(() => {});

  // Also sync chat client
  selectChatClient(clientId, clientName);

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
  setTimeout(() => clientSearch.focus(), 10);
}

function closeDropdown() {
  clientDropdown.classList.add('hidden');
  clientPickerBtn.classList.remove('open');
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('#client-picker')) closeDropdown();
  if (!e.target.closest('#chat-client-picker')) closeChatDropdown();
});

clientSearch.addEventListener('input', () => {
  renderClientList(clientSearch.value);
});

clientSearch.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeDropdown(); return; }
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
      chrome.storage.session.set({ auto_match_result: result }).catch(() => {});
      renderClientList();
      selectClient(result.client_id, result.client_name || getClientName(result.client_id));
    } else {
      resetPickerText();
    }
  } catch {
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
    const results = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: () => window.getSelection().toString(),
    });
    const text = results?.[0]?.result?.trim();
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
// Parsed content detection (Gmail emails, QBO, tax software)
// ---------------------------------------------------------------------------

async function detectParsedContent() {
  if (!activeTab?.id) return;

  // Full parser detection via content script (for capture data)
  try {
    const response = await chrome.tabs.sendMessage(activeTab.id, { type: 'GET_PARSED_CONTENT' });
    if (response?.parsed) {
      parsedContent = response;
      if (response.document_tag) {
        const option = tagSelect.querySelector(`option[value="${response.document_tag}"]`);
        if (option) tagSelect.value = response.document_tag;
      }
      if (response.capture_type) {
        setMode(response.capture_type === 'text_selection' ? 'text' : 'page');
      }
      updatePreview();
    }
  } catch { /* content script not available */ }

  // Lightweight badge detection via executeScript (works even without content script)
  await detectParserBadge();
}

async function detectParserBadge() {
  // Tier gate: parsers are a paid feature
  if (extensionConfig && !extensionConfig.parsers) return;

  if (!activeTab?.id || !activeTab?.url) return;

  // Skip if user dismissed badge on this tab
  if (dismissedBadgeTabId === activeTab.id) return;

  // Skip restricted URLs
  const url = activeTab.url;
  if (url.startsWith('chrome://') || url.startsWith('chrome-extension://') || url.startsWith('about:')) {
    clearParserBadge();
    return;
  }

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: activeTab.id },
      func: () => {
        const host = location.hostname;

        // Gmail
        if (host === 'mail.google.com') {
          // Check for an open email (subject line in main content)
          const subject = document.querySelector('h2[data-thread-perm-id], h2.hP, div[role="main"] h2');
          if (subject) {
            return { detected: true, platform: 'gmail', label: 'Gmail email detected', icon: '\u{1F4E7}', document_tag_suggestion: 'correspondence' };
          }
          return { detected: false };
        }

        // QuickBooks Online
        if (host === 'qbo.intuit.com' || host.endsWith('.qbo.intuit.com') || host === 'quickbooks.intuit.com' || host.endsWith('.quickbooks.intuit.com')) {
          // Check for report vs transaction
          const reportHeader = document.querySelector('[data-testid="report-header"], .report-header, #reportContainer');
          if (reportHeader) {
            return { detected: true, platform: 'quickbooks', label: 'QuickBooks report detected', icon: '\u{1F4CA}', document_tag_suggestion: 'financial_statement' };
          }
          const txn = document.querySelector('[data-testid="transaction-form"], .txn-detail, form[name*="transaction"]');
          if (txn) {
            return { detected: true, platform: 'quickbooks', label: 'QuickBooks transaction detected', icon: '\u{1F4B0}', document_tag_suggestion: 'financial_statement' };
          }
          return { detected: false };
        }

        // Tax software — exact suffix match to avoid false positives
        const taxHosts = ['drakesoftware.com', 'drakecpe.com', 'lacerte.intuit.com', 'cs.thomsonreuters.com', 'proseries.intuit.com', 'pro.taxact.com'];
        if (taxHosts.some(h => host === h || host.endsWith('.' + h))) {
          return { detected: true, platform: 'tax', label: 'Tax return data detected', icon: '\u{1F3DB}', document_tag_suggestion: 'tax_document' };
        }

        return { detected: false };
      },
    });

    const result = results?.[0]?.result;
    if (result?.detected) {
      showParserBadge(result);
    } else {
      clearParserBadge();
    }
  } catch {
    clearParserBadge();
  }
}

function showParserBadge(detection) {
  clearParserBadge(true); // clear without animation

  const { platform, icon, label, document_tag_suggestion } = detection;

  // Auto-set document tag
  if (document_tag_suggestion) {
    const option = tagSelect.querySelector(`option[value="${document_tag_suggestion}"]`);
    if (option) tagSelect.value = document_tag_suggestion;
  }

  // Build badge HTML
  const tintClass = platform === 'gmail' ? 'badge-gmail' :
                    platform === 'quickbooks' ? 'badge-quickbooks' :
                    platform === 'tax' ? 'badge-tax' : '';

  let html = `<div class="parser-badge ${tintClass}">
    <span class="parser-badge-icon">${icon}</span>
    <span class="parser-badge-label">${escapeHtml(label)}${platform === 'tax' ? ' \u2014 PII auto-masked' : ''}</span>
    <button class="parser-badge-dismiss" title="Dismiss">&times;</button>
  </div>`;

  if (platform === 'tax') {
    html += `<div class="tax-warning">This capture may contain tax return information subject to IRC \u00A77216. Ensure client consent is obtained before AI processing.</div>`;
  }

  parserBadgeBar.innerHTML = html;
  parserBadgeBar.classList.remove('hidden');

  // Dismiss handler
  const dismissBtn = parserBadgeBar.querySelector('.parser-badge-dismiss');
  if (dismissBtn) {
    dismissBtn.addEventListener('click', () => {
      dismissedBadgeTabId = activeTab?.id || null;
      const badge = parserBadgeBar.querySelector('.parser-badge');
      if (badge) {
        badge.classList.add('dismissing');
        setTimeout(() => clearParserBadge(), 150);
      } else {
        clearParserBadge();
      }
    });
  }
}

function clearParserBadge(instant) {
  if (!instant && parserBadgeBar.innerHTML) {
    // Animate out if there's content
    const badge = parserBadgeBar.querySelector('.parser-badge');
    if (badge && !badge.classList.contains('dismissing')) {
      badge.classList.add('dismissing');
      setTimeout(() => {
        parserBadgeBar.innerHTML = '';
        parserBadgeBar.classList.add('hidden');
      }, 150);
      return;
    }
  }
  parserBadgeBar.innerHTML = '';
  parserBadgeBar.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Recent captures (collapsible section in capture panel)
// ---------------------------------------------------------------------------

let recentLastFetched = 0;
const RECENT_CACHE_TTL = 60 * 1000; // 60 seconds

const CAPTURE_TYPE_ICONS = {
  text_selection: '📝',
  full_page: '📄',
  file_url: '📎',
  screenshot: '📸',
  email: '✉️',
};

recentToggleBtn.addEventListener('click', () => {
  const isOpen = recentToggleBtn.classList.contains('open');
  recentToggleBtn.classList.toggle('open', !isOpen);
  recentListEl.classList.toggle('hidden', isOpen);
  if (!isOpen) loadRecentCaptures();
});

recentRefreshBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  recentLastFetched = 0; // force refresh
  loadRecentCaptures();
});

async function loadRecentCaptures(force = false) {
  if (!force && Date.now() - recentLastFetched < RECENT_CACHE_TTL) return;

  // Show loading skeleton
  recentListEl.innerHTML = Array.from({ length: 3 }, () =>
    `<div class="recent-skeleton">
      <div class="skel-icon"></div>
      <div class="skel-body">
        <div class="skel-line skel-line-long"></div>
        <div class="skel-line skel-line-short"></div>
      </div>
    </div>`
  ).join('');
  recentListEl.classList.remove('hidden');
  recentSection.classList.remove('hidden');
  recentRefreshBtn.classList.add('spinning');

  try {
    const captures = await getRecentCaptures();
    const items = Array.isArray(captures) ? captures : (captures?.captures || []);
    recentLastFetched = Date.now();

    if (items.length === 0) {
      recentListEl.innerHTML = '<div class="rules-empty"><p>No recent captures yet.</p></div>';
      recentRefreshBtn.classList.remove('spinning');
      return;
    }

    const recent = items.slice(0, 10);
    const html = recent.map(c => {
      const icon = CAPTURE_TYPE_ICONS[c.capture_type] || '📄';
      const name = c.filename || c.capture_type?.replace(/_/g, ' ') || 'Capture';
      const truncName = name.length > 35 ? name.slice(0, 32) + '...' : name;
      const client = c.client_name || 'Unknown';
      const time = c.created_at ? formatRelativeTime(c.created_at) : '';
      const docId = c.document_id || '';
      const clientId = c.client_id || '';
      const href = clientId ? `${CONFIG.APP_URL}/dashboard/clients/${clientId}` : '';
      return `<div class="recent-item" ${href ? `data-href="${escapeHtml(href)}"` : ''}>
        <span class="recent-type-icon">${icon}</span>
        <div class="recent-item-body">
          <div class="recent-filename">${escapeHtml(truncName)}</div>
          <div class="recent-item-meta">
            <span class="recent-client-badge">${escapeHtml(client)}</span>
            ${time ? `<span class="recent-time">${time}</span>` : ''}
          </div>
        </div>
      </div>`;
    }).join('');

    recentListEl.innerHTML = html +
      `<a class="recent-view-all" href="${CONFIG.APP_URL}/dashboard" target="_blank">View all in Callwen →</a>`;

    // Make items clickable
    recentListEl.querySelectorAll('.recent-item[data-href]').forEach(el => {
      el.addEventListener('click', () => {
        chrome.tabs.create({ url: el.dataset.href });
      });
    });

    // Open the section if collapsed
    if (!recentToggleBtn.classList.contains('open')) {
      recentToggleBtn.classList.add('open');
      recentListEl.classList.remove('hidden');
    }
  } catch { /* non-critical */ }
  recentRefreshBtn.classList.remove('spinning');
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
        const truncated = selectedText.length > 200 ? selectedText.slice(0, 200) + '...' : selectedText;
        previewBody.innerHTML = escapeHtml(truncated);
      } else {
        previewBody.innerHTML = '<span class="preview-placeholder">Select text on the page, then capture</span>';
      }
      break;

    case 'page':
      if (parsedContent?.parser === 'tax_software' && parsedContent.tax_data) {
        const td = parsedContent.tax_data;
        const sw = parsedContent.software_name || 'Tax Software';
        const client = td.client_name ? `Client: ${td.client_name}` : '';
        const form = td.form_type ? `Form ${td.form_type}` : '';
        const year = td.tax_year ? `Tax Year ${td.tax_year}` : '';
        const detail = [form, year].filter(Boolean).join(' \u{2014} ');
        previewBody.innerHTML =
          `<span class="preview-title">${escapeHtml(sw)}</span>` +
          (client ? `<span class="preview-url">${escapeHtml(client)}</span>` : '') +
          (detail ? `<span class="preview-url">${escapeHtml(detail)}</span>` : '');
      } else if (parsedContent?.parser === 'quickbooks' && parsedContent.qbo_data) {
        const qd = parsedContent.qbo_data;
        if (parsedContent.qbo_page_type === 'report') {
          const title = qd.report_title || 'Report';
          const company = qd.company_name ? `Company: ${qd.company_name}` : '';
          const period = qd.date_range ? `Period: ${qd.date_range}` : '';
          previewBody.innerHTML =
            `<span class="preview-title">${escapeHtml(title)}</span>` +
            (company ? `<span class="preview-url">${escapeHtml(company)}</span>` : '') +
            (period ? `<span class="preview-url">${escapeHtml(period)}</span>` : '');
        } else {
          const txnType = qd.transaction_type || 'Transaction';
          const entity = qd.vendor_or_customer || '';
          const amount = qd.amount || '';
          const detail = [entity, amount].filter(Boolean).join(' — ');
          previewBody.innerHTML =
            `<span class="preview-title">${escapeHtml(txnType)}${qd.transaction_number ? ` #${escapeHtml(qd.transaction_number)}` : ''}</span>` +
            (detail ? `<span class="preview-url">${escapeHtml(detail)}</span>` : '');
        }
      } else if (activeTab) {
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

    case 'screenshot': {
      const title = activeTab?.title ? escapeHtml(activeTab.title) : 'Current page';
      const url = activeTab?.url ? escapeHtml(activeTab.url) : '';
      previewBody.innerHTML =
        `<span class="preview-title">\u{1F4F8} Captures the visible area of the current page</span>` +
        (url ? `<span class="preview-url">${title}</span>` : '');
      break;
    }

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
      activeTab = await getActiveTab();
    }

    const tabId = activeTab?.id;
    let captureType = '';
    let capturePayload = '';

    switch (activeMode) {
      case 'text':
        if (parsedContent?.content) {
          captureType = 'text_selection';
          capturePayload = parsedContent.content;
        } else {
          // Get selected text directly — no content script needed
          const selResults = await chrome.scripting.executeScript({
            target: { tabId },
            func: () => window.getSelection().toString(),
          });
          const selText = selResults?.[0]?.result?.trim();
          if (!selText) {
            showStatus('No text selected on the page. Select some text first.', 'error');
            setBtnLoading(false);
            return;
          }
          captureType = 'text_selection';
          capturePayload = selText.slice(0, CONFIG.MAX_TEXT_LENGTH);
        }
        break;

      case 'page':
        if (parsedContent?.content && parsedContent.capture_type === 'full_page') {
          captureType = 'full_page';
          capturePayload = parsedContent.content;
        } else {
          // Get page text directly — no content script needed
          const pageResults = await chrome.scripting.executeScript({
            target: { tabId },
            func: (maxLen) => (document.body?.innerText || '').substring(0, maxLen),
            args: [CONFIG.MAX_TEXT_LENGTH],
          });
          const pageText = pageResults?.[0]?.result?.trim();
          if (!pageText) {
            showStatus('No content found on this page.', 'error');
            setBtnLoading(false);
            return;
          }
          captureType = 'full_page';
          capturePayload = pageText;
        }
        break;

      case 'file': {
        const session = await chrome.storage.session.get('pending_capture');
        const pending = session?.pending_capture;
        if (!pending?.data?.fileUrl) {
          showStatus('No file link captured. Right-click a link to capture.', 'error');
          setBtnLoading(false);
          return;
        }
        const filePayload = await captureFileUrl(pending.data.fileUrl);
        captureType = filePayload.type;
        capturePayload = filePayload.file_url;
        break;
      }

      case 'screenshot': {
        captureBtnText.textContent = 'Capturing...';
        // Use broadcast pattern — sendResponse is unreliable in MV3 service workers
        const ssResult = await new Promise((resolve) => {
          const timeout = setTimeout(() => {
            chrome.runtime.onMessage.removeListener(listener);
            resolve({ error: 'Screenshot timed out. Please try again.' });
          }, 10000);
          function listener(msg) {
            if (msg.type === 'SCREENSHOT_CAPTURED') {
              clearTimeout(timeout);
              chrome.runtime.onMessage.removeListener(listener);
              resolve(msg);
            }
          }
          chrome.runtime.onMessage.addListener(listener);
          chrome.runtime.sendMessage({ type: 'CAPTURE_VISIBLE_TAB' }).catch(() => {});
        });
        if (ssResult.error) {
          showStatus(ssResult.error, 'error');
          setBtnLoading(false);
          return;
        }
        if (!ssResult.imageData) {
          showStatus('Screenshot capture failed. Please try again.', 'error');
          setBtnLoading(false);
          return;
        }
        captureType = 'screenshot';
        capturePayload = ssResult.imageData;
        break;
      }
    }

    const metadata = {
      url: activeTab?.url || '',
      page_title: activeTab?.title || '',
      captured_at: new Date().toISOString(),
      site_domain: activeTab?.url ? extractDomain(activeTab.url) : '',
    };

    const isScreenshot = captureType === 'screenshot';
    await captureContent(
      clientId, captureType,
      isScreenshot ? null : capturePayload,
      metadata, tag,
      isScreenshot ? capturePayload : null,
    );

    await addRecentClientId(clientId);

    setBtnLoading(false);
    showBtnSuccess();


    // Refresh recent captures list
    recentLastFetched = 0;
    loadRecentCaptures();

    chrome.runtime.sendMessage({ type: 'CAPTURE_COMPLETE' }).catch(() => {});

    if (extensionConfig) {
      extensionConfig.captures_today = (extensionConfig.captures_today || 0) + 1;
      if (extensionConfig.captures_per_day > 0) {
        extensionConfig.captures_remaining = Math.max(0,
          (extensionConfig.captures_remaining || 0) - 1);
      }
      updateUsage(extensionConfig);
      updateFooterUsage(extensionConfig);
    }

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

  clientPickerBtn.disabled = loading;
}

function showBtnSuccess() {
  captureBtn.classList.add('btn-success');
  captureBtnText.classList.add('hidden');
  captureSpinner.classList.add('hidden');
  captureCheck.classList.remove('hidden');

  // Reset after 3 seconds
  setTimeout(() => {
    captureBtn.classList.remove('btn-success');
    captureCheck.classList.add('hidden');
    captureBtnText.classList.remove('hidden');
    updateCaptureButton();
  }, 3000);
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
// Footer usage bar (persistent across all tabs)
// ---------------------------------------------------------------------------

function updateFooterUsage(config) {
  if (!config) return;

  usageFooter.classList.remove('hidden');

  const used = config.captures_today || 0;
  const total = config.captures_per_day;
  const tier = config.tier || 'free';
  const tierLabel = tier.charAt(0).toUpperCase() + tier.slice(1);

  footerTierBadge.textContent = tierLabel;

  // Unlimited (firm tier or captures_per_day is null/-1)
  if (!total || total === -1) {
    footerUsageText.textContent = `${used} captures today`;
    footerProgressBar.style.width = '100%';
    footerProgressBar.className = 'footer-progress-bar';
    footerProgressTrack.style.display = '';
    footerUpgrade.classList.add('hidden');
    usageFooter.title = `You've used ${used} captures today. Unlimited on your plan.`;
    return;
  }

  const remaining = config.captures_remaining ?? (total - used);
  const pct = Math.min(100, (used / total) * 100);
  const atLimit = remaining <= 0;

  // Text
  if (atLimit) {
    footerUsageText.textContent = 'Daily limit reached';
  } else {
    footerUsageText.textContent = `${used} / ${total} captures today`;
  }

  // Progress bar color
  footerProgressBar.style.width = `${pct}%`;
  footerProgressBar.classList.remove('bar-warning', 'bar-danger');
  if (pct >= 100) {
    footerProgressBar.classList.add('bar-danger');
  } else if (pct >= 80) {
    footerProgressBar.classList.add('bar-warning');
  }

  // Upgrade link
  if (atLimit) {
    footerUpgrade.classList.remove('hidden');
    if (tier === 'free') {
      footerUpgrade.classList.add('prominent');
    } else {
      footerUpgrade.classList.remove('prominent');
    }
  } else {
    footerUpgrade.classList.add('hidden');
  }

  usageFooter.title = `You've used ${used} of ${total} daily captures. Resets at midnight UTC.`;
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

// ===========================================================================
// CHAT PANEL (Quick Query)
// ===========================================================================

// ---------------------------------------------------------------------------
// Chat client picker
// ---------------------------------------------------------------------------

function renderChatClientList(filter = '') {
  const query = filter.toLowerCase().trim();
  const sorted = [...allClients].sort((a, b) =>
    (a.name || '').localeCompare(b.name || ''));

  const recentSet = new Set(recentClientIds);
  const recentClients = recentClientIds
    .map(id => sorted.find(c => c.id === id))
    .filter(Boolean);
  const otherClients = sorted.filter(c => !recentSet.has(c.id));

  const matchFn = (c) => {
    if (!query) return true;
    return (c.name || '').toLowerCase().includes(query) ||
           (c.business_name || '').toLowerCase().includes(query);
  };

  let html = '';

  const filteredRecent = recentClients.filter(matchFn);
  if (filteredRecent.length > 0 && !query) {
    html += '<div class="sp-client-divider">Recently used</div>';
    filteredRecent.slice(0, 3).forEach(c => {
      html += chatClientOptionHtml(c);
    });
  }

  const list = query ? sorted.filter(matchFn) : otherClients;
  if (list.length > 0) {
    if (!query) html += '<div class="sp-client-divider">All clients</div>';
    list.forEach(c => {
      if (!query && recentSet.has(c.id)) return;
      html += chatClientOptionHtml(c);
    });
  }

  if (!html) {
    html = '<div class="sp-client-empty">No clients found</div>';
  }

  chatClientList.innerHTML = html;

  chatClientList.querySelectorAll('.sp-client-option').forEach(el => {
    el.addEventListener('click', () => {
      selectChatClient(el.dataset.id, el.dataset.name);
      closeChatDropdown();
    });
  });
}

function chatClientOptionHtml(c) {
  const sel = c.id === chatSelectedClientId ? ' selected' : '';
  const label = c.business_name ? `${c.name} — ${c.business_name}` : c.name;
  return `<div class="sp-client-option${sel}" data-id="${c.id}" data-name="${escapeHtml(c.name || 'Unnamed')}">${escapeHtml(label)}</div>`;
}

function selectChatClient(id, name) {
  if (chatSelectedClientId && chatSelectedClientId !== id) {
    clearChat();
  }

  chatSelectedClientId = id;
  chatSelectedClientName = name;
  chatClientText.textContent = name;
  chatClientText.classList.remove('placeholder');
  queryInput.disabled = false;
  queryInput.placeholder = `Ask about ${name}'s documents...`;
  updateSendBtn();

  chatClientList.querySelectorAll('.sp-client-option').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === id);
  });

  chrome.storage.session.set({
    selected_client_id: id,
    selected_client_name: name,
  }).catch(() => {});
}

chatClientBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  if (chatClientDropdown.classList.contains('hidden')) openChatDropdown();
  else closeChatDropdown();
});

function openChatDropdown() {
  chatClientDropdown.classList.remove('hidden');
  chatClientBtn.classList.add('open');
  chatClientSearch.value = '';
  renderChatClientList();
  setTimeout(() => chatClientSearch.focus(), 10);
}

function closeChatDropdown() {
  chatClientDropdown.classList.add('hidden');
  chatClientBtn.classList.remove('open');
}

chatClientSearch.addEventListener('input', () => {
  renderChatClientList(chatClientSearch.value);
});

chatClientSearch.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeChatDropdown(); return; }
  if (e.key === 'Enter') {
    const first = chatClientList.querySelector('.sp-client-option');
    if (first) {
      selectChatClient(first.dataset.id, first.dataset.name);
      closeChatDropdown();
    }
  }
});

// ---------------------------------------------------------------------------
// Selected text context (for chat)
// ---------------------------------------------------------------------------

async function checkSelectedTextForChat() {
  try {
    const tab = await getActiveTab();
    if (!tab?.id) return;
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });
    const text = results?.[0]?.result?.trim();
    if (text && text.length > 0) {
      selectedText = text;
      contextBanner.classList.remove('hidden');
    }
  } catch { /* no access */ }
}

insertContextBtn.addEventListener('click', () => {
  if (!selectedText) return;
  const quote = selectedText.length > 500
    ? selectedText.slice(0, 500) + '...'
    : selectedText;
  queryInput.value = `> ${quote.replace(/\n/g, '\n> ')}\n\n`;
  autoResizeInput();
  queryInput.focus();
  contextBanner.classList.add('hidden');
});

dismissContextBtn.addEventListener('click', () => {
  contextBanner.classList.add('hidden');
  selectedText = '';
});

// ---------------------------------------------------------------------------
// Chat messages
// ---------------------------------------------------------------------------

function clearChat() {
  chatHistory = [];
  chatMessages.innerHTML = `
    <div class="chat-empty">
      <p class="chat-empty-title">Ask anything</p>
      <p class="chat-empty-desc">Questions are answered using your client's uploaded documents with source citations.</p>
    </div>`;
}

function addUserMessage(text) {
  const empty = chatMessages.querySelector('.chat-empty');
  if (empty) empty.remove();

  chatHistory.push({ role: 'user', content: text });

  const el = document.createElement('div');
  el.className = 'msg-user';
  el.textContent = text;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function addTypingIndicator() {
  const el = document.createElement('div');
  el.className = 'msg-typing';
  el.id = 'typing-indicator';
  el.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  chatMessages.appendChild(el);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

function addAiMessage(answer, confidenceTier, confidenceScore, sources) {
  chatHistory.push({
    role: 'ai', content: answer,
    confidence: confidenceTier, score: confidenceScore, sources,
  });

  const el = document.createElement('div');
  el.className = 'msg-ai';

  const tier = (confidenceTier || 'medium').toLowerCase();
  const pct = confidenceScore != null ? formatScore(confidenceScore) : '';
  const tierLabel = tier.charAt(0).toUpperCase() + tier.slice(1);

  let html = `<div class="confidence-row">
    <span class="confidence-dot ${tier}"></span>
    <span class="confidence-label">${tierLabel} confidence</span>
    ${pct ? `<span class="confidence-pct">${pct}</span>` : ''}
  </div>`;

  html += `<div class="msg-ai-text">${escapeHtml(answer)}</div>`;

  if (sources && sources.length > 0) {
    html += '<div class="sources-row">';
    sources.forEach((src, i) => {
      const name = src.document_name || src.filename || `Source ${i + 1}`;
      const score = src.score != null ? formatScore(src.score) : '';
      html += `<div class="source-pill" data-idx="${i}">
        <span class="source-pill-name">${escapeHtml(name)}</span>
        ${score ? `<span class="source-pill-score">${score}</span>` : ''}
      </div>`;
    });
    html += '</div>';
    sources.forEach((src, i) => {
      const preview = src.chunk_text || src.content || '';
      if (preview) {
        html += `<div class="source-preview hidden" data-preview-idx="${i}">${escapeHtml(preview.slice(0, 300))}</div>`;
      }
    });
  }

  el.innerHTML = html;

  el.querySelectorAll('.source-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const idx = pill.dataset.idx;
      const preview = el.querySelector(`[data-preview-idx="${idx}"]`);
      if (preview) preview.classList.toggle('hidden');
    });
  });

  chatMessages.appendChild(el);
  scrollToBottom();
}

function addErrorMessage(text) {
  const el = document.createElement('div');
  el.className = 'msg-ai';
  el.innerHTML = `<div class="msg-ai-text" style="color: #ef4444;">${escapeHtml(text)}</div>`;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ---------------------------------------------------------------------------
// Send question
// ---------------------------------------------------------------------------

async function handleSend() {
  const question = queryInput.value.trim();
  if (!question || !chatSelectedClientId) return;

  const now = Date.now();
  const recentQueries = queryTimestamps.filter(t => now - t < 60000);
  if (recentQueries.length >= 3) {
    throttleMsg.classList.remove('hidden');
    setTimeout(() => throttleMsg.classList.add('hidden'), 3000);
    return;
  }
  queryTimestamps.push(now);

  queryInput.value = '';
  autoResizeInput();
  updateSendBtn();

  addUserMessage(question);
  addTypingIndicator();
  setInputEnabled(false);

  try {
    const response = await askQuestion(chatSelectedClientId, question);

    removeTypingIndicator();

    const answer = response.response || response.answer || response.message || 'No answer available.';
    const confidenceTier = response.confidence_tier || response.confidence || 'medium';
    const confidenceScore = response.confidence_score ?? response.score ?? null;
    const sources = response.sources || response.citations || [];

    addAiMessage(answer, confidenceTier, confidenceScore, sources);
  } catch (err) {
    removeTypingIndicator();

    if (err.code === ERROR_CODES.AUTH_EXPIRED) {
      addErrorMessage('Session expired. Please sign in again.');
      showScreen('auth');
      return;
    }
    addErrorMessage(err.message || 'Something went wrong. Please try again.');
  }

  setInputEnabled(true);
  queryInput.focus();
}

function setInputEnabled(enabled) {
  queryInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

function updateSendBtn() {
  sendBtn.disabled = !queryInput.value.trim() || !chatSelectedClientId;
}

sendBtn.addEventListener('click', handleSend);

queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

queryInput.addEventListener('input', () => {
  autoResizeInput();
  updateSendBtn();
});

function autoResizeInput() {
  queryInput.style.height = 'auto';
  queryInput.style.height = Math.min(queryInput.scrollHeight, 80) + 'px';
}

// ===========================================================================
// RULES PANEL
// ===========================================================================

let rulesLoaded = false;

async function loadRules() {
  if (extensionConfig && extensionConfig.monitoring_enabled === false) {
    rulesListEl.classList.add('hidden');
    rulesAddSection.classList.add('hidden');
    rulesForm.classList.add('hidden');
    rulesGate.classList.remove('hidden');
    return;
  }

  rulesGate.classList.add('hidden');

  if (rulesLoaded) return;

  try {
    const result = await getMonitoringRules();
    monitoringRules = Array.isArray(result) ? result : (result?.rules || []);
    rulesLoaded = true;
    renderRules();
  } catch (err) {
    if (err.code === ERROR_CODES.TIER_UPGRADE) {
      rulesListEl.classList.add('hidden');
      rulesAddSection.classList.add('hidden');
      rulesForm.classList.add('hidden');
      rulesGate.classList.remove('hidden');
    } else {
      rulesListEl.innerHTML = '<div class="rules-empty"><p>Failed to load rules.</p></div>';
    }
  }
}

function renderRules() {
  if (monitoringRules.length === 0) {
    rulesListEl.innerHTML = '<div class="rules-empty"><p>No monitoring rules yet.</p><p style="font-size:11px;color:#475569;">Rules auto-capture pages matching your patterns.</p></div>';
    rulesAddSection.classList.remove('hidden');
    return;
  }

  rulesAddSection.classList.remove('hidden');

  const html = monitoringRules.map(rule => {
    const icon = getRuleTypeIcon(rule.rule_type || rule.type);
    const clientName = rule.client_name || getClientName(rule.client_id) || 'Unknown';
    const isActive = rule.is_active !== false;
    const pattern = rule.pattern || '';

    return `<div class="rule-item" data-rule-id="${rule.id}">
      <div class="rule-type-icon">${icon}</div>
      <div class="rule-info">
        <div class="rule-name">${escapeHtml(rule.name || 'Unnamed rule')}</div>
        <div class="rule-detail">${escapeHtml(pattern)} → ${escapeHtml(clientName)}</div>
      </div>
      <div class="rule-actions">
        <button class="toggle${isActive ? ' on' : ''}" data-action="toggle" data-rule-id="${rule.id}" title="${isActive ? 'Disable' : 'Enable'}"></button>
        <button class="rule-delete" data-action="delete" data-rule-id="${rule.id}" title="Delete rule">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
          </svg>
        </button>
      </div>
    </div>`;
  }).join('');

  rulesListEl.innerHTML = html;

  rulesListEl.querySelectorAll('[data-action="toggle"]').forEach(btn => {
    btn.addEventListener('click', () => handleToggleRule(btn.dataset.ruleId));
  });

  rulesListEl.querySelectorAll('[data-action="delete"]').forEach(btn => {
    btn.addEventListener('click', () => handleDeleteRule(btn.dataset.ruleId));
  });
}

function getRuleTypeIcon(type) {
  switch (type) {
    case 'domain': return '\u{1F310}';
    case 'url_contains': return '\u{1F517}';
    case 'email_from': return '\u{1F4E7}';
    case 'page_title': return '\u{1F4C4}';
    default: return '\u{1F50D}';
  }
}

async function handleToggleRule(ruleId) {
  const rule = monitoringRules.find(r => r.id === ruleId);
  if (!rule) return;

  const newState = rule.is_active === false ? true : false;

  rule.is_active = newState;
  const toggleBtn = rulesListEl.querySelector(`[data-action="toggle"][data-rule-id="${ruleId}"]`);
  if (toggleBtn) toggleBtn.classList.toggle('on', newState);

  try {
    await updateMonitoringRule(ruleId, { is_active: newState });
    chrome.runtime.sendMessage({ type: 'MONITORING_RULES_CHANGED' }).catch(() => {});
  } catch {
    rule.is_active = !newState;
    if (toggleBtn) toggleBtn.classList.toggle('on', !newState);
  }
}

async function handleDeleteRule(ruleId) {
  const rule = monitoringRules.find(r => r.id === ruleId);
  const ruleName = rule?.name || 'this rule';

  const confirmed = await showConfirmDialog(`Delete "${ruleName}"? This cannot be undone.`);
  if (!confirmed) return;

  try {
    await deleteMonitoringRule(ruleId);
    monitoringRules = monitoringRules.filter(r => r.id !== ruleId);
    renderRules();
    chrome.runtime.sendMessage({ type: 'MONITORING_RULES_CHANGED' }).catch(() => {});
  } catch (err) {
    handleApiError(err);
  }
}

function showConfirmDialog(message) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    overlay.innerHTML = `<div class="confirm-dialog">
      <p>${escapeHtml(message)}</p>
      <div class="confirm-actions">
        <button class="btn-ghost" data-confirm="cancel">Cancel</button>
        <button class="btn-danger" data-confirm="ok">Delete</button>
      </div>
    </div>`;

    document.body.appendChild(overlay);

    const cleanup = (result) => {
      overlay.remove();
      resolve(result);
    };

    overlay.querySelector('[data-confirm="cancel"]').addEventListener('click', () => cleanup(false));
    overlay.querySelector('[data-confirm="ok"]').addEventListener('click', () => cleanup(true));
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) cleanup(false);
    });
  });
}

// --- Add rule form ---

addRuleBtn.addEventListener('click', () => {
  showRulesForm();
});

rulesFormCancel.addEventListener('click', () => {
  hideRulesForm();
});

function showRulesForm(prefill = {}) {
  rulesForm.classList.remove('hidden');
  rulesAddSection.classList.add('hidden');

  const clientOptions = allClients.map(c =>
    `<option value="${c.id}">${escapeHtml(c.name || 'Unnamed')}</option>`
  ).join('');
  ruleClientSelect.innerHTML = `<option value="">Select a client...</option>${clientOptions}`;

  ruleNameInput.value = prefill.name || '';
  ruleTypeSelect.value = prefill.rule_type || 'domain';
  rulePatternInput.value = prefill.pattern || '';
  if (prefill.client_id) ruleClientSelect.value = prefill.client_id;

  updatePatternPlaceholder();
  validateRuleForm();

  setTimeout(() => ruleNameInput.focus(), 10);
}

function hideRulesForm() {
  rulesForm.classList.add('hidden');
  rulesAddSection.classList.remove('hidden');
  ruleNameInput.value = '';
  rulePatternInput.value = '';
  ruleClientSelect.value = '';
}

ruleTypeSelect.addEventListener('change', updatePatternPlaceholder);

function updatePatternPlaceholder() {
  const placeholders = {
    domain: 'e.g., acmecorp.com',
    url_contains: 'e.g., /invoices/',
    email_from: 'e.g., cfo@acmecorp.com',
    page_title: 'e.g., Profit & Loss',
  };
  rulePatternInput.placeholder = placeholders[ruleTypeSelect.value] || 'Enter pattern...';
}

ruleNameInput.addEventListener('input', validateRuleForm);
rulePatternInput.addEventListener('input', validateRuleForm);
ruleClientSelect.addEventListener('change', validateRuleForm);

function validateRuleForm() {
  const valid = ruleNameInput.value.trim() &&
                rulePatternInput.value.trim() &&
                ruleClientSelect.value;
  ruleSaveBtn.disabled = !valid;
}

ruleSaveBtn.addEventListener('click', handleSaveRule);

async function handleSaveRule() {
  const name = ruleNameInput.value.trim();
  const ruleType = ruleTypeSelect.value;
  const pattern = rulePatternInput.value.trim();
  const clientId = ruleClientSelect.value;

  if (!name || !pattern || !clientId) return;

  ruleSaveBtn.disabled = true;
  ruleSaveText.classList.add('hidden');
  ruleSaveSpinner.classList.remove('hidden');

  try {
    const newRule = await createMonitoringRule({
      name,
      rule_type: ruleType,
      pattern,
      client_id: clientId,
    });

    if (newRule) {
      monitoringRules.push(newRule);
    } else {
      rulesLoaded = false;
      await loadRules();
    }

    hideRulesForm();
    renderRules();

    chrome.runtime.sendMessage({ type: 'MONITORING_RULES_CHANGED' }).catch(() => {});
  } catch (err) {
    handleApiError(err);
  } finally {
    ruleSaveBtn.disabled = false;
    ruleSaveText.classList.remove('hidden');
    ruleSaveSpinner.classList.add('hidden');
  }
}

// --- Quick rule creation from auto-match ---

createRuleFromMatch.addEventListener('click', (e) => {
  e.preventDefault();
  switchPanel('rules');

  const prefill = {
    client_id: autoMatchResult?.client_id || selectedClientId || '',
  };

  if (activeTab?.url) {
    try {
      const domain = new URL(activeTab.url).hostname;
      prefill.rule_type = 'domain';
      prefill.pattern = domain;
      prefill.name = `Capture from ${domain}`;
    } catch {}
  }

  showRulesForm(prefill);
});

// ===========================================================================
// MONITORING TOGGLE (bell icon in header)
// ===========================================================================

async function initMonitoringToggle() {
  try {
    const response = await new Promise(resolve => {
      chrome.runtime.sendMessage({ type: 'GET_MONITORING_PREFS' }, resolve);
    });
    if (response) monitoringPrefs = response;
  } catch { /* use defaults */ }
  updateBellIcon();
}

function updateBellIcon() {
  const isMuted = monitoringPrefs.muted_until && Date.now() < monitoringPrefs.muted_until;
  const isOff = !monitoringPrefs.enabled || isMuted;
  monitoringToggle.classList.toggle('muted', isOff);
  monitoringToggle.title = isOff
    ? (isMuted ? 'Monitoring: muted' : 'Monitoring: off')
    : 'Monitoring: active';
}

monitoringToggle.addEventListener('click', async () => {
  monitoringPrefs.enabled = !monitoringPrefs.enabled;
  if (monitoringPrefs.enabled) monitoringPrefs.muted_until = 0;
  updateBellIcon();
  chrome.runtime.sendMessage({
    type: 'SET_MONITORING_PREFS',
    prefs: monitoringPrefs,
  }).catch(() => {});
});

monitoringToggle.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  showMuteMenu();
});

function showMuteMenu() {
  closeMuteMenu();

  const menu = document.createElement('div');
  menu.id = 'mute-menu';
  menu.className = 'mute-menu';
  menu.innerHTML = `
    <button class="mute-menu-item" data-mute="3600000">Mute for 1 hour</button>
    <button class="mute-menu-item" data-mute="28800000">Mute for 8 hours</button>
    <button class="mute-menu-item" data-mute="0">Unmute</button>
  `;

  monitoringToggle.parentElement.style.position = 'relative';
  monitoringToggle.parentElement.appendChild(menu);

  menu.querySelectorAll('.mute-menu-item').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const duration = parseInt(e.target.dataset.mute, 10);
      monitoringPrefs.muted_until = duration ? Date.now() + duration : 0;
      if (duration) monitoringPrefs.enabled = true;
      updateBellIcon();
      chrome.runtime.sendMessage({
        type: 'SET_MONITORING_PREFS',
        prefs: monitoringPrefs,
      }).catch(() => {});
      closeMuteMenu();
    });
  });

  setTimeout(() => {
    document.addEventListener('click', closeMuteMenuOnOutsideClick);
  }, 10);
}

function closeMuteMenu() {
  const existing = document.getElementById('mute-menu');
  if (existing) existing.remove();
  document.removeEventListener('click', closeMuteMenuOnOutsideClick);
}

function closeMuteMenuOnOutsideClick(e) {
  if (!e.target.closest('#mute-menu') && !e.target.closest('#monitoring-toggle')) {
    closeMuteMenu();
  }
}

// ===========================================================================
// AUTH EVENTS
// ===========================================================================

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
    autoMatchResult = null;
    selectedText = '';
    dismissedBadgeTabId = null;

    clearParserBadge(true);
    tagSelect.value = 'other';
    chrome.storage.session.remove('auto_match_result').catch(() => {});
    if (extensionConfig?.auto_match && message.tab?.url) {
      activeTab = message.tab;
      tryAutoMatch();
    } else {
      resetPickerText();
    }
    updatePreview();
    checkSelectedTextForChat();
    detectParserBadge();
  }
});

// Direct tab activation listener — more reliable than relying on service worker relay
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    dismissedBadgeTabId = null;
    clearParserBadge(true);
    tagSelect.value = 'other';
    if (tab.url && !tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
      activeTab = tab;
      autoMatchResult = null;
      selectedText = '';
      updatePreview();
      detectParsedContent();
    }
  } catch { /* tab may not exist */ }
});

// Sync auth and client state from local storage changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local') {
    // Auth token added or changed → auto-transition to authenticated view
    if (changes.callwen_auth_token) {
      const newToken = changes.callwen_auth_token.newValue;
      if (newToken) {
        // Only re-init if we're currently showing the sign-in screen
        if (authScreen && !authScreen.classList.contains('hidden')) {
          init();
        }
      } else {
        // Token removed → show sign-in
        allClients = [];
        extensionConfig = null;
        chatHistory = [];
        selectedClientId = '';
        showScreen('auth');
      }
    }

    // Cached clients updated from another context (e.g. service worker)
    if (changes.callwen_cached_clients && changes.callwen_cached_clients.newValue) {
      const cached = changes.callwen_cached_clients.newValue;
      const clients = cached.clients || cached;
      if (Array.isArray(clients) && clients.length > 0 && mainScreen && !mainScreen.classList.contains('hidden')) {
        allClients = clients;
        renderClientList();
        renderChatClientList();
      }
    }
    return;
  }

  if (area !== 'session') return;

  if (changes.selected_client_id && changes.selected_client_id.newValue) {
    const id = changes.selected_client_id.newValue;
    const name = changes.selected_client_name?.newValue || getClientName(id);

    // Sync capture picker
    if (id !== selectedClientId && allClients.some(c => c.id === id)) {
      selectedClientId = id;
      clientSelectHidden.value = id;
      clientPickerText.textContent = name;
      clientPickerText.classList.remove('placeholder');
      clientListEl.querySelectorAll('.client-option').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === id);
      });
      updateCaptureButton();
    }

    // Sync chat picker
    if (id !== chatSelectedClientId && allClients.some(c => c.id === id)) {
      selectChatClient(id, name);
    }
  }
});

// ===========================================================================
// HELPERS
// ===========================================================================

function formatScore(raw) {
  let s = raw;
  if (s > 100) s = s / 100;
  if (s > 0 && s <= 1) s = s * 100;
  return s.toFixed(1) + '%';
}

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

// ===========================================================================
// BOOT
// ===========================================================================

init();
