/**
 * Clerk authentication for the extension.
 *
 * The extension doesn't run its own Clerk instance. Instead it opens a tab to
 * Callwen's sign-in page and listens for the session token via a message from
 * the content script running on callwen.com.
 */

import { CONFIG } from '../utils/config.js';
import { getAuthToken, setAuthToken, clearAuthToken } from '../utils/storage.js';

/**
 * Check if the user has a valid auth token stored.
 */
export async function isAuthenticated() {
  const token = await getAuthToken();
  return token !== null;
}

/**
 * Open the Callwen sign-in page so the user can authenticate.
 * The content script on callwen.com will detect the Clerk session
 * and send the token back via chrome.runtime.sendMessage.
 */
export async function signIn() {
  await chrome.tabs.create({ url: `${CONFIG.APP_URL}/sign-in?source=extension` });
}

/**
 * Clear the stored auth token (sign out).
 */
export async function signOut() {
  await clearAuthToken();
}

/**
 * Handle an incoming auth token from the content script on callwen.com.
 */
export async function handleAuthToken(token) {
  if (token) {
    await setAuthToken(token);
  }
}
