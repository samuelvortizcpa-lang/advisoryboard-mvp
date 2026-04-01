/**
 * Chrome storage helpers.
 *
 * Only stores auth token and client name/ID pairs.
 * NEVER store document content, email bodies, or client-specific data.
 */

const KEYS = {
  AUTH_TOKEN: 'callwen_auth_token',
  CACHED_CLIENTS: 'callwen_cached_clients',
};

// ---------------------------------------------------------------------------
// Auth token
// ---------------------------------------------------------------------------

export async function getAuthToken() {
  const result = await chrome.storage.local.get(KEYS.AUTH_TOKEN);
  return result[KEYS.AUTH_TOKEN] || null;
}

export async function setAuthToken(token) {
  await chrome.storage.local.set({ [KEYS.AUTH_TOKEN]: token });
}

export async function clearAuthToken() {
  await chrome.storage.local.remove(KEYS.AUTH_TOKEN);
}

// ---------------------------------------------------------------------------
// Cached clients (names and IDs only)
// ---------------------------------------------------------------------------

export async function getCachedClients() {
  const result = await chrome.storage.local.get(KEYS.CACHED_CLIENTS);
  return result[KEYS.CACHED_CLIENTS] || null;
}

export async function setCachedClients(clients) {
  // Only store id and name — strip any other fields
  const safe = clients.map(({ id, name }) => ({ id, name }));
  await chrome.storage.local.set({ [KEYS.CACHED_CLIENTS]: safe });
}

// ---------------------------------------------------------------------------
// Clear all
// ---------------------------------------------------------------------------

export async function clearAll() {
  await chrome.storage.local.remove(Object.values(KEYS));
}
