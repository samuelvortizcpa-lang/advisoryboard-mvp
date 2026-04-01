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
  // Just open the auth callback page. The content script running on that page
  // will detect the ?token= parameter and relay it to the service worker via
  // AUTH_TOKEN_FROM_PAGE message. No tabs.onUpdated watcher needed.
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
  await clearAll();
}

// ---------------------------------------------------------------------------
// Auth check — token exists in storage (no API call)
// Expired tokens are caught by the API client's 401 handler which clears storage.
// ---------------------------------------------------------------------------

export async function isAuthenticated() {
  const token = await getAuthToken();
  return !!token;
}

// ---------------------------------------------------------------------------
// Refresh session — opens callwen.com briefly to refresh the Clerk session
// ---------------------------------------------------------------------------

export async function refreshSession() {
  // Open the callback page in the background. The content script will detect
  // the token and relay it via AUTH_TOKEN_FROM_PAGE. The service worker closes
  // the tab after receiving the token.
  await chrome.tabs.create({
    url: `${CONFIG.APP_URL}/extension-auth-callback?refresh=true`,
    active: false,
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
