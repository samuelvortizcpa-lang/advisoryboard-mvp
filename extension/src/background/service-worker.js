/**
 * Background service worker for the Callwen extension.
 *
 * Handles:
 * - Context menu registration
 * - Message routing between popup, content script, and sidepanel
 * - Auth token relay from callwen.com content script
 */

import { handleAuthToken } from '../services/auth.js';

// ---------------------------------------------------------------------------
// Context menus
// ---------------------------------------------------------------------------

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'callwen-capture-selection',
    title: 'Capture selection to Callwen',
    contexts: ['selection'],
  });

  chrome.contextMenus.create({
    id: 'callwen-capture-page',
    title: 'Capture full page to Callwen',
    contexts: ['page'],
  });

  chrome.contextMenus.create({
    id: 'callwen-capture-link',
    title: 'Capture linked file to Callwen',
    contexts: ['link'],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  // Forward to popup for client selection
  chrome.runtime.sendMessage({
    type: 'CONTEXT_MENU_CAPTURE',
    menuItemId: info.menuItemId,
    linkUrl: info.linkUrl,
    selectionText: info.selectionText,
    tab: { id: tab.id, url: tab.url, title: tab.title },
  });
});

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'AUTH_TOKEN') {
    handleAuthToken(message.token).then(() => sendResponse({ ok: true }));
    return true; // async response
  }

  if (message.type === 'OPEN_SIDEPANEL') {
    chrome.sidePanel.open({ windowId: sender.tab?.windowId });
    sendResponse({ ok: true });
    return false;
  }
});
