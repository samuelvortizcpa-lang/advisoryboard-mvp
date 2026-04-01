/**
 * Popup UI logic.
 */

import { CONFIG } from '../utils/config.js';
import { isAuthenticated, signIn, signOut } from '../services/auth.js';
import { getExtensionConfig, getClients } from '../services/api.js';
import { captureTextSelection, captureFullPage, captureScreenshot } from '../services/capture.js';
import { setCachedClients } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const authScreen = document.getElementById('auth-screen');
const mainScreen = document.getElementById('main-screen');
const signInBtn = document.getElementById('sign-in-btn');
const signOutBtn = document.getElementById('sign-out-btn');
const clientSelect = document.getElementById('client-select');
const tagSelect = document.getElementById('tag-select');
const captureSelectionBtn = document.getElementById('capture-selection');
const capturePageBtn = document.getElementById('capture-page');
const captureScreenshotBtn = document.getElementById('capture-screenshot');
const statusEl = document.getElementById('status');
const usageEl = document.getElementById('usage');
const usageText = document.getElementById('usage-text');

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  const authed = await isAuthenticated();

  if (!authed) {
    authScreen.classList.remove('hidden');
    mainScreen.classList.add('hidden');
    return;
  }

  authScreen.classList.add('hidden');
  mainScreen.classList.remove('hidden');

  // Populate tag selector
  tagSelect.innerHTML = CONFIG.DOCUMENT_TAGS
    .map(t => `<option value="${t.value}">${t.label}</option>`)
    .join('');

  // Load clients and config in parallel
  try {
    const [config, clientsRes] = await Promise.all([
      getExtensionConfig(),
      getClients(),
    ]);

    // Populate client selector
    const clients = clientsRes.clients || clientsRes;
    clientSelect.innerHTML = '<option value="">Select a client...</option>' +
      clients.map(c => `<option value="${c.id}">${c.name}</option>`).join('');

    // Cache client list for content script
    await setCachedClients(clients.map(c => ({ id: c.id, name: c.name })));

    // Show usage
    if (config.captures_per_day !== null) {
      usageEl.classList.remove('hidden');
      const remaining = config.captures_remaining ?? (config.captures_per_day - config.captures_today);
      usageText.textContent = `${remaining} captures remaining today (${config.tier} plan)`;
    }
  } catch (err) {
    showStatus(err.message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

signInBtn.addEventListener('click', () => signIn());

signOutBtn.addEventListener('click', async () => {
  await signOut();
  authScreen.classList.remove('hidden');
  mainScreen.classList.add('hidden');
});

captureSelectionBtn.addEventListener('click', () => handleCapture('selection'));
capturePageBtn.addEventListener('click', () => handleCapture('page'));
captureScreenshotBtn.addEventListener('click', () => handleCapture('screenshot'));

async function handleCapture(type) {
  const clientId = clientSelect.value;
  if (!clientId) {
    showStatus('Please select a client first.', 'error');
    return;
  }

  const tag = tagSelect.value;
  showStatus('Capturing...', 'loading');
  disableButtons(true);

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    let result;
    if (type === 'selection') {
      result = await captureTextSelection(tab, clientId, tag);
    } else if (type === 'page') {
      result = await captureFullPage(tab, clientId, tag);
    } else if (type === 'screenshot') {
      result = await captureScreenshot(tab, clientId, tag);
    }

    let msg = `Captured to ${result.client_name}`;
    if (result.warning) msg += ` — ${result.warning}`;
    showStatus(msg, 'success');
  } catch (err) {
    showStatus(err.message, 'error');
  } finally {
    disableButtons(false);
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function showStatus(message, type) {
  statusEl.textContent = message;
  statusEl.className = `status ${type}`;
  statusEl.classList.remove('hidden');

  if (type === 'success') {
    setTimeout(() => statusEl.classList.add('hidden'), 4000);
  }
}

function disableButtons(disabled) {
  captureSelectionBtn.disabled = disabled;
  capturePageBtn.disabled = disabled;
  captureScreenshotBtn.disabled = disabled;
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

init();
