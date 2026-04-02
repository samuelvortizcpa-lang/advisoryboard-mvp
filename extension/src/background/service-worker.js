/**
 * Background service worker for the Callwen extension.
 *
 * Handles:
 * - Context menu registration and click handlers
 * - Auth callback listener (captures token from /extension-auth-callback)
 * - Badge management (daily capture count)
 * - Passive monitoring: rule matching on page navigation + email sender checks
 * - Message routing between popup, content script, and sidepanel
 */

import { CONFIG } from '../utils/config.js';
import { handleAuthToken, getToken, isAuthenticated } from '../services/auth.js';
import { getExtensionConfig } from '../services/api.js';
import {
  checkPage, checkEmailSender, showMatchNotification,
  loadRules, invalidateRulesCache, isMonitoringActive,
} from '../services/monitoring.js';

const AUTH_CALLBACK_PREFIX = `${CONFIG.APP_URL}/extension-auth-callback`;

// ---------------------------------------------------------------------------
// Context menus — register on install
// ---------------------------------------------------------------------------

chrome.runtime.onInstalled.addListener(() => {
  // Make the toolbar icon open the side panel instead of a popup
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

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

  chrome.contextMenus.create({
    id: 'callwen-ask-about',
    title: 'Ask Callwen about this',
    contexts: ['selection'],
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

    case 'callwen-ask-about': {
      // Open side panel with the selected text as a query
      const quote = (info.selectionText || '').slice(0, 500);
      await chrome.storage.session.set({
        sidepanel_query: `> ${quote}\n\nWhat does this mean?`,
      });
      chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
      return;
    }

    default:
      return;
  }

  // Store the pending capture in session storage so the side panel can pick it up on init
  const pendingPayload = {
    capture_type: captureType,
    data: captureData,
    tab: { id: tab.id, url: tab.url, title: tab.title },
    timestamp: Date.now(),
  };
  await chrome.storage.session.set({ pending_capture: pendingPayload });

  // Open the side panel for client selection
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});

  // Also broadcast to the side panel in case it's already open (sidePanel.open is a no-op then)
  chrome.runtime.sendMessage({
    type: 'CONTEXT_MENU_CAPTURE',
    capture_type: captureType,
    data: captureData,
  }).catch(() => { /* side panel may not be open yet */ });
});

// ---------------------------------------------------------------------------
// Auth callback listener (old tabs.onUpdated approach removed — now handled
// by content script sending AUTH_TOKEN_FROM_PAGE message)
// ---------------------------------------------------------------------------

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
// Passive monitoring — check pages on navigation
// ---------------------------------------------------------------------------

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  // Only check when a page finishes loading
  if (changeInfo.status !== 'complete') return;
  if (!tab.url || tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) return;

  // Skip auth callback URLs (handled above)
  if (tab.url.startsWith(AUTH_CALLBACK_PREFIX)) return;

  try {
    // Check if user is authenticated
    const authenticated = await isAuthenticated();
    if (!authenticated) return;

    // Check if monitoring is active (enabled + not muted)
    const active = await isMonitoringActive();
    if (!active) return;

    const domain = new URL(tab.url).hostname.toLowerCase();
    const matches = await checkPage(tabId, tab.url, domain);

    if (matches.length > 0) {
      await showMatchNotification(tabId, tab.url, matches);
    }
  } catch {
    // Best-effort — don't disrupt browsing
  }
});

// ---------------------------------------------------------------------------
// Tab change handling — clear auto-match and notify views
// ---------------------------------------------------------------------------

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    // Clear stale auto-match when switching tabs
    await chrome.storage.session.remove('auto_match_result');

    // Broadcast tab change to popup and sidepanel
    chrome.runtime.sendMessage({
      type: 'TAB_CHANGED',
      tab: { id: tab.id, url: tab.url, title: tab.title },
    }).catch(() => { /* views may not be open */ });
  } catch { /* tab may not exist */ }
});

// ---------------------------------------------------------------------------
// Notification click handler
// ---------------------------------------------------------------------------

chrome.notifications.onClicked.addListener(async (notificationId) => {
  if (notificationId.startsWith('monitoring-')) {
    // Open the side panel
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
    } catch { /* best effort */ }
    chrome.notifications.clear(notificationId);
  }
});

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  // Content script detected ?token= on /extension-auth-callback
  if (message.type === 'AUTH_TOKEN_FROM_PAGE') {
    console.log('[Callwen SW] Received token from content script');
    (async () => {
      try {
        await handleAuthToken(message.token);
        await updateBadge();
        console.log('[Callwen SW] Token stored successfully');
        loadRules(true).catch(() => {});

        // Notify sidepanel that auth state changed
        chrome.runtime.sendMessage({ type: 'AUTH_STATE_CHANGED', authenticated: true })
          .catch(() => { /* views may not be open */ });

        sendResponse({ ok: true });

        // Close the auth tab after a short delay so the sendResponse
        // completes and the content script receives confirmation
        setTimeout(() => {
          if (sender.tab?.id) {
            chrome.tabs.remove(sender.tab.id).catch(() => {});
          }
        }, 500);
      } catch (err) {
        console.error('[Callwen SW] Error storing token:', err);
        sendResponse({ ok: false });
      }
    })();
    return true; // async
  }

  // Clerk cookie relay from content script on callwen.com
  if (message.type === 'AUTH_TOKEN') {
    handleAuthToken(message.token)
      .then(() => updateBadge())
      .then(() => {
        loadRules(true).catch(() => {});
        sendResponse({ ok: true });
      });
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

  // Monitoring: rules were modified in the popup — refresh cache
  if (message.type === 'MONITORING_RULES_CHANGED') {
    invalidateRulesCache()
      .then(() => loadRules(true))
      .then(() => sendResponse({ ok: true }))
      .catch(() => sendResponse({ ok: false }));
    return true; // async
  }

  // Monitoring: email sender check from parsed content
  if (message.type === 'CHECK_EMAIL_SENDER') {
    (async () => {
      try {
        const matches = await checkEmailSender(message.email_addresses);
        if (matches.length > 0 && message.tab_id) {
          const url = message.url || '';
          await showMatchNotification(message.tab_id, url, matches);
        }
        sendResponse({ matches });
      } catch {
        sendResponse({ matches: [] });
      }
    })();
    return true; // async
  }

  // Screenshot capture — broadcast pattern (sendResponse is unreliable in MV3)
  if (message.type === 'CAPTURE_VISIBLE_TAB') {
    (async () => {
      try {
        console.log('[Callwen SW] CAPTURE_VISIBLE_TAB received');
        const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        if (!tabs || tabs.length === 0) {
          chrome.runtime.sendMessage({ type: 'SCREENSHOT_CAPTURED', error: 'No active tab found.' });
          return;
        }
        const tab = tabs[0];
        console.log('[Callwen SW] Capturing tab:', tab.id, tab.url);
        const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
        const base64 = dataUrl.replace(/^data:image\/png;base64,/, '');
        console.log('[Callwen SW] Screenshot captured, broadcasting result');
        chrome.runtime.sendMessage({ type: 'SCREENSHOT_CAPTURED', imageData: base64 });
      } catch (err) {
        console.error('[Callwen SW] Screenshot error:', err);
        chrome.runtime.sendMessage({ type: 'SCREENSHOT_CAPTURED', error: 'Cannot capture this page. Try a different tab.' });
      }
    })();
    return false; // not using sendResponse
  }

  // Monitoring preferences
  if (message.type === 'GET_MONITORING_PREFS') {
    import('../services/monitoring.js').then(m => m.getMonitoringPrefs())
      .then(prefs => sendResponse(prefs))
      .catch(() => sendResponse({ enabled: true, muted_until: 0 }));
    return true;
  }

  if (message.type === 'SET_MONITORING_PREFS') {
    import('../services/monitoring.js').then(m => m.setMonitoringPrefs(message.prefs))
      .then(updated => sendResponse(updated))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }
});
