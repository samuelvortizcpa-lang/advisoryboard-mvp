/**
 * Background service worker for the Callwen extension.
 *
 * Handles:
 * - Context menu registration and click handlers
 * - Auth callback listener (captures token from /extension-auth-callback)
 * - Badge management (daily capture count)
 * - Monitoring rule checks on page navigation
 * - Message routing between popup, content script, and sidepanel
 */

import { CONFIG } from '../utils/config.js';
import { handleAuthToken, getToken, isAuthenticated } from '../services/auth.js';
import { getExtensionConfig, checkMonitoringRules } from '../services/api.js';

const AUTH_CALLBACK_PREFIX = `${CONFIG.APP_URL}/extension-auth-callback`;

// ---------------------------------------------------------------------------
// Context menus — register on install
// ---------------------------------------------------------------------------

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'callwen-capture-selection',
    title: 'Capture selection to Callwen',
    contexts: ['selection'],
  });

  chrome.contextMenus.create({
    id: 'callwen-capture-page',
    title: 'Capture this page to Callwen',
    contexts: ['page'],
  });

  chrome.contextMenus.create({
    id: 'callwen-capture-link',
    title: 'Capture linked file to Callwen',
    contexts: ['link'],
  });
});

// ---------------------------------------------------------------------------
// Context menu click handlers
// ---------------------------------------------------------------------------

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id) return;

  let captureType = '';
  let captureData = {};

  switch (info.menuItemId) {
    case 'callwen-capture-selection':
      captureType = 'text_selection';
      captureData = { text: info.selectionText || '' };
      break;

    case 'callwen-capture-page': {
      // Inject script to grab full page text
      try {
        const [result] = await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: () => document.body?.innerText || '',
        });
        captureType = 'full_page';
        captureData = { text: result?.result || '' };
      } catch {
        captureType = 'full_page';
        captureData = { text: '' };
      }
      break;
    }

    case 'callwen-capture-link':
      captureType = 'file_url';
      captureData = { fileUrl: info.linkUrl || '' };
      break;

    default:
      return;
  }

  // Store the pending capture in session storage so the popup can pick it up
  await chrome.storage.session.set({
    pending_capture: {
      capture_type: captureType,
      data: captureData,
      tab: { id: tab.id, url: tab.url, title: tab.title },
      timestamp: Date.now(),
    },
  });

  // Open the popup for client selection
  chrome.action.openPopup().catch(() => {
    // openPopup() may not be supported in all environments — fall back
    // to sending a message that the popup listens for on open
  });
});

// ---------------------------------------------------------------------------
// Auth callback listener
// ---------------------------------------------------------------------------

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  if (!changeInfo.url || !changeInfo.url.startsWith(AUTH_CALLBACK_PREFIX)) return;

  try {
    const url = new URL(changeInfo.url);
    const token = url.searchParams.get('token');
    if (token) {
      await handleAuthToken(token);
      await updateBadge();

      // Notify popup that auth state changed
      chrome.runtime.sendMessage({ type: 'AUTH_STATE_CHANGED', authenticated: true })
        .catch(() => { /* popup may not be open */ });
    }

    // Close the auth tab
    chrome.tabs.remove(tabId).catch(() => {});
  } catch {
    // Malformed URL — ignore
  }
});

// ---------------------------------------------------------------------------
// Badge management
// ---------------------------------------------------------------------------

async function updateBadge() {
  try {
    const token = await getToken();
    if (!token) {
      chrome.action.setBadgeText({ text: '' });
      return;
    }

    const config = await getExtensionConfig();
    const remaining = config.captures_remaining;
    const total = config.captures_per_day;

    if (total === -1) {
      // Unlimited (firm tier)
      chrome.action.setBadgeText({ text: '' });
      return;
    }

    if (remaining <= 0) {
      chrome.action.setBadgeText({ text: '0' });
      chrome.action.setBadgeBackgroundColor({ color: '#DC2626' }); // red
    } else {
      chrome.action.setBadgeText({ text: String(remaining) });
      chrome.action.setBadgeBackgroundColor({ color: '#16A34A' }); // green
    }
  } catch {
    chrome.action.setBadgeText({ text: '' });
  }
}

// Update badge on startup and every 5 minutes
updateBadge();
setInterval(updateBadge, 5 * 60 * 1000);

// ---------------------------------------------------------------------------
// Monitoring rule check on page navigation
// ---------------------------------------------------------------------------

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  // Only check when a page finishes loading
  if (changeInfo.status !== 'complete') return;
  if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) return;

  try {
    // Check if user is authenticated and has monitoring enabled
    const authenticated = await isAuthenticated();
    if (!authenticated) return;

    const config = await getExtensionConfig();
    if (!config.monitoring) return;

    // Ask content script for page metadata
    let pageData;
    try {
      pageData = await chrome.tabs.sendMessage(tabId, { type: 'GET_PAGE_METADATA' });
    } catch {
      // Content script not injected on this page
      return;
    }

    if (!pageData) return;

    // Check against monitoring rules
    const result = await checkMonitoringRules(pageData);
    if (!result?.matches?.length) return;

    const topMatch = result.matches[0];

    // Show a notification
    chrome.notifications.create(`monitoring-${tabId}-${Date.now()}`, {
      type: 'basic',
      iconUrl: 'assets/icon-128.png',
      title: 'Callwen — Client Page Detected',
      message: `This page may be related to ${topMatch.client_name}. Open the extension to capture it.`,
      priority: 1,
    });
  } catch {
    // Best-effort — don't disrupt browsing
  }
});

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'AUTH_TOKEN') {
    handleAuthToken(message.token)
      .then(() => updateBadge())
      .then(() => sendResponse({ ok: true }));
    return true; // async
  }

  if (message.type === 'OPEN_SIDEPANEL') {
    chrome.sidePanel.open({ windowId: sender.tab?.windowId });
    sendResponse({ ok: true });
    return false;
  }

  if (message.type === 'CAPTURE_COMPLETE') {
    // Refresh badge after a capture
    updateBadge();
    sendResponse({ ok: true });
    return false;
  }

  if (message.type === 'GET_AUTH_STATE') {
    getToken()
      .then(token => sendResponse({ authenticated: !!token }))
      .catch(() => sendResponse({ authenticated: false }));
    return true; // async
  }

  if (message.type === 'UPDATE_BADGE') {
    updateBadge().then(() => sendResponse({ ok: true }));
    return true; // async
  }
});
