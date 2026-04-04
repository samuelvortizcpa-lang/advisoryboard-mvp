/**
 * Clerk authentication for the extension.
 *
 * The extension can't run Clerk's JS SDK directly. Instead it opens a tab to
 * /extension-auth-callback. If the user is already signed in, the page gets
 * a JWT from Clerk and appends ?token=<jwt> to the URL. If not signed in,
 * the page redirects to /sign-in which returns here after auth. The service
 * worker listens for the callback URL, extracts the token, and stores it.
 *
 * Token refresh:
 * - Proactive: a timer fires 10s before JWT `exp` to silently fetch a new token
 * - Reactive: on 401 the API client calls silentRefresh() before showing sign-in
 */

import { CONFIG } from '../utils/config.js';
import { getAuthToken, setAuthToken, clearAuthToken, clearAll } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// Refresh state (module-level, lives as long as the service worker)
// ---------------------------------------------------------------------------

let refreshTimer = null;
let isRefreshing = false;
let refreshFailCount = 0;
const MAX_REFRESH_RETRIES = 3;

// ---------------------------------------------------------------------------
// Sign in — opens callwen.com sign-in, waits for callback
// ---------------------------------------------------------------------------

export async function signIn() {
  await chrome.tabs.create({ url: `${CONFIG.APP_URL}/extension-auth-callback` });
}

// ---------------------------------------------------------------------------
// Token access
// ---------------------------------------------------------------------------

export async function getToken() {
  return getAuthToken();
}

// ---------------------------------------------------------------------------
// Sign out
// ---------------------------------------------------------------------------

export async function signOut() {
  cancelRefreshTimer();
  await clearAll();
}

// ---------------------------------------------------------------------------
// Auth check — token exists in storage (no API call)
// ---------------------------------------------------------------------------

export async function isAuthenticated() {
  const token = await getAuthToken();
  return !!token;
}

// ---------------------------------------------------------------------------
// Handle incoming auth token (from content script relay)
// ---------------------------------------------------------------------------

export async function handleAuthToken(token) {
  if (token) {
    await setAuthToken(token);
    refreshFailCount = 0; // successful token → reset retry counter
    scheduleProactiveRefresh(token);
  }
}

// ---------------------------------------------------------------------------
// JWT expiry decoding
// ---------------------------------------------------------------------------

function getTokenExpiry(token) {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    // Base64url decode the payload
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const decoded = JSON.parse(atob(payload));
    return decoded.exp ? decoded.exp * 1000 : null; // convert to ms
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Proactive refresh — schedule timer before JWT expires
// ---------------------------------------------------------------------------

const REFRESH_BUFFER_MS = 10_000; // refresh 10s before expiry

export function scheduleProactiveRefresh(token) {
  cancelRefreshTimer();

  const expiry = getTokenExpiry(token);
  if (!expiry) {
    return;
  }

  const msUntilRefresh = expiry - Date.now() - REFRESH_BUFFER_MS;
  if (msUntilRefresh <= 0) {
    silentRefresh().catch(() => {});
    return;
  }

  // MV3 service workers can sleep, but chrome.alarms is more reliable for
  // long durations. For Clerk's ~60s tokens, setTimeout works fine since
  // the SW stays alive during active use.
  refreshTimer = setTimeout(() => {
    silentRefresh().catch(() => {});

  }, msUntilRefresh);
}

export function cancelRefreshTimer() {
  if (refreshTimer) {
    clearTimeout(refreshTimer);
    refreshTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Silent refresh — open background tab to get fresh token
// ---------------------------------------------------------------------------

const SILENT_REFRESH_TIMEOUT_MS = 8_000;

export async function silentRefresh() {
  // Guard: only one refresh at a time
  if (isRefreshing) {
    throw new Error('Refresh already in progress');
  }

  // Guard: stop retrying after MAX_REFRESH_RETRIES consecutive failures
  if (refreshFailCount >= MAX_REFRESH_RETRIES) {
    await clearAuthToken();
    throw new Error('Max refresh retries exceeded');
  }

  isRefreshing = true;
  try {
    const token = await _doSilentRefresh();
    refreshFailCount = 0;
    return token;
  } catch (err) {
    refreshFailCount++;
    if (refreshFailCount >= MAX_REFRESH_RETRIES) {
      await clearAuthToken();
    }
    throw err;
  } finally {
    isRefreshing = false;
  }
}

function _doSilentRefresh() {
  return new Promise((resolve, reject) => {
    let tabId = null;
    let settled = false;

    function cleanup() {
      if (tabId) {
        chrome.tabs.remove(tabId).catch(() => {});
        tabId = null;
      }
    }

    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      chrome.runtime.onMessage.removeListener(listener);
      cleanup();
      reject(new Error('Silent refresh timed out'));
    }, SILENT_REFRESH_TIMEOUT_MS);

    function listener(message, sender) {
      if (settled) return;
      if (message.type !== 'AUTH_TOKEN_FROM_PAGE') return;
      // Only accept tokens from our auth callback tab
      if (sender.tab?.id !== tabId) return;

      settled = true;
      clearTimeout(timeout);
      chrome.runtime.onMessage.removeListener(listener);

      resolve(message.token);

      // Close the background tab after a short delay so the message channel settles
      setTimeout(cleanup, 300);
    }

    chrome.runtime.onMessage.addListener(listener);

    // Open the auth callback page in a background tab
    chrome.tabs.create({
      url: `${CONFIG.APP_URL}/extension-auth-callback?refresh=true`,
      active: false,
    }).then((tab) => {
      tabId = tab.id;
    }).catch((err) => {
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        chrome.runtime.onMessage.removeListener(listener);
        cleanup();
        reject(err);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Initialize refresh timer on service worker startup
// ---------------------------------------------------------------------------

export async function initRefreshTimer() {
  const token = await getAuthToken();
  if (token) {
    scheduleProactiveRefresh(token);
  }
}
