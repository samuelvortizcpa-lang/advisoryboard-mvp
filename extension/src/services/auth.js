/**
 * Clerk authentication for the extension.
 *
 * The extension can't run Clerk's JS SDK directly. Instead it opens a tab to
 * /extension-auth-callback. If the user is already signed in, the page gets
 * a JWT from Clerk and appends ?token=<jwt> to the URL. If not signed in,
 * the page redirects to /sign-in which returns here after auth. The service
 * worker listens for the callback URL, extracts the token, and stores it.
 */

import { CONFIG } from '../utils/config.js';
import { getAuthToken, setAuthToken, clearAuthToken, clearAll } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// Sign in — opens callwen.com sign-in, waits for callback
// ---------------------------------------------------------------------------

export async function signIn() {
  return new Promise((resolve, reject) => {
    const callbackPrefix = `${CONFIG.APP_URL}/extension-auth-callback`;
    let authTabId = null;
    let settled = false;

    const cleanup = () => {
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timeout);
    };

    const settle = async (token, error) => {
      if (settled) return;
      settled = true;
      cleanup();

      // Close the auth tab if it's still open
      if (authTabId !== null) {
        try { await chrome.tabs.remove(authTabId); } catch { /* already closed */ }
      }

      if (error) return reject(error);
      resolve(token);
    };

    // Timeout after 5 minutes — user may have closed the tab
    const timeout = setTimeout(() => {
      settle(null, new Error('Sign-in timed out. Please try again.'));
    }, 5 * 60 * 1000);

    // Watch for the callback URL
    const listener = async (tabId, changeInfo) => {
      if (changeInfo.url && changeInfo.url.startsWith(callbackPrefix)) {
        try {
          const url = new URL(changeInfo.url);
          const token = url.searchParams.get('token');
          if (!token) {
            return settle(null, new Error('No token in callback URL.'));
          }
          await setAuthToken(token);
          settle(token, null);
        } catch (err) {
          settle(null, err);
        }
      }
    };

    chrome.tabs.onUpdated.addListener(listener);

    // Open sign-in page
    chrome.tabs.create({ url: `${CONFIG.APP_URL}/extension-auth-callback` })
      .then(tab => { authTabId = tab.id; })
      .catch(err => settle(null, err));
  });
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
  await clearAll();
}

// ---------------------------------------------------------------------------
// Auth check — verifies the stored token is still valid
// ---------------------------------------------------------------------------

export async function isAuthenticated() {
  const token = await getAuthToken();
  if (!token) return false;

  try {
    const res = await fetch(`${CONFIG.API_BASE_URL}/api/users/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok;
  } catch {
    // Network error — can't verify, but token exists
    return false;
  }
}

// ---------------------------------------------------------------------------
// Refresh session — opens callwen.com briefly to refresh the Clerk session
// ---------------------------------------------------------------------------

export async function refreshSession() {
  return new Promise((resolve, reject) => {
    const callbackPrefix = `${CONFIG.APP_URL}/extension-auth-callback`;
    let refreshTabId = null;
    let settled = false;

    const cleanup = () => {
      chrome.tabs.onUpdated.removeListener(listener);
      clearTimeout(timeout);
    };

    const settle = async (token, error) => {
      if (settled) return;
      settled = true;
      cleanup();

      if (refreshTabId !== null) {
        try { await chrome.tabs.remove(refreshTabId); } catch { /* already closed */ }
      }

      if (error) return reject(error);
      resolve(token);
    };

    const timeout = setTimeout(() => {
      settle(null, new Error('Session refresh timed out.'));
    }, 30 * 1000);

    const listener = async (tabId, changeInfo) => {
      if (changeInfo.url && changeInfo.url.startsWith(callbackPrefix)) {
        try {
          const url = new URL(changeInfo.url);
          const token = url.searchParams.get('token');
          if (token) {
            await setAuthToken(token);
            settle(token, null);
          } else {
            settle(null, new Error('No token in refresh callback.'));
          }
        } catch (err) {
          settle(null, err);
        }
      }
    };

    chrome.tabs.onUpdated.addListener(listener);

    // Open callwen.com in the background — if user has an active session,
    // Clerk auto-authenticates and the app redirects to the callback
    chrome.tabs.create({
      url: `${CONFIG.APP_URL}/extension-auth-callback?refresh=true`,
      active: false,
    })
      .then(tab => { refreshTabId = tab.id; })
      .catch(err => settle(null, err));
  });
}

// ---------------------------------------------------------------------------
// Handle incoming auth token (from content script relay)
// ---------------------------------------------------------------------------

export async function handleAuthToken(token) {
  if (token) {
    await setAuthToken(token);
  }
}
