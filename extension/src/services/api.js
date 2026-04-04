/**
 * API client for Callwen backend.
 *
 * All extension API calls go through here so auth headers and error handling
 * are consistent. Every request includes the Clerk JWT as Bearer token.
 *
 * On 401, attempts a silent token refresh before giving up. This keeps the
 * user signed in even when the short-lived Clerk JWT expires between actions.
 */

import { CONFIG } from '../utils/config.js';
import { getAuthToken, clearAuthToken, setCachedClients } from '../utils/storage.js';
import { silentRefresh } from './auth.js';

// ---------------------------------------------------------------------------
// Error codes used by the popup to display contextual messages
// ---------------------------------------------------------------------------

const ERROR_CODES = {
  AUTH_EXPIRED: 'auth_expired',
  TIER_UPGRADE: 'tier_upgrade',
  RATE_LIMITED: 'rate_limited',
  SERVER_ERROR: 'server_error',
};

// ---------------------------------------------------------------------------
// Core request function
// ---------------------------------------------------------------------------

async function request(path, options = {}, _retried = false) {
  const token = await getAuthToken();
  if (!token) {
    // No token at all — try a silent refresh before giving up
    if (!_retried) {
      try {
        await silentRefresh();
        return request(path, options, true);
      } catch { /* refresh failed */ }
    }
    const err = new Error('Not authenticated. Please sign in to Callwen.');
    err.status = 401;
    err.code = ERROR_CODES.AUTH_EXPIRED;
    throw err;
  }

  const url = `${CONFIG.API_BASE_URL}/api${path}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    ...options.headers,
  };

  let response;
  try {
    response = await fetch(url, { ...options, headers });
  } catch (networkErr) {
    const err = new Error('Callwen is temporarily unavailable. Check your connection.');
    err.status = 0;
    err.code = ERROR_CODES.SERVER_ERROR;
    throw err;
  }

  if (response.ok) {
    if (response.status === 204) return null;
    return response.json();
  }

  // --- 401: attempt silent refresh and retry once ---

  if (response.status === 401 && !_retried) {
    try {
      await silentRefresh();
      return request(path, options, true);
    } catch {
      // Refresh failed — fall through to 401 handling
    }
    // Refresh failed — fall through to normal 401 handling
    await clearAuthToken();
    const err = new Error('Session expired. Please sign in again.');
    err.status = 401;
    err.code = ERROR_CODES.AUTH_EXPIRED;
    throw err;
  }

  // --- Error handling by status code ---

  let body = {};
  try { body = await response.json(); } catch { /* non-JSON response */ }
  const detail = body.detail || `Request failed (${response.status})`;

  const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  err.status = response.status;

  if (response.status === 401) {
    await clearAuthToken();
    err.code = ERROR_CODES.AUTH_EXPIRED;
    err.message = 'Session expired. Please sign in again.';
  } else if (response.status === 403) {
    err.code = ERROR_CODES.TIER_UPGRADE;
    err.upgradeUrl = body.upgrade_url || `${CONFIG.APP_URL}/dashboard/settings`;
  } else if (response.status === 429) {
    err.code = ERROR_CODES.RATE_LIMITED;
    err.message = body.detail || 'Daily capture limit reached. Upgrade for more.';
  } else if (response.status >= 500) {
    err.code = ERROR_CODES.SERVER_ERROR;
    err.message = 'Callwen is temporarily unavailable. Please try again later.';
  }

  throw err;
}

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export async function getClients() {
  const data = await request('/clients');
  // Backend returns { items: [...], total, skip, limit }
  const clients = Array.isArray(data) ? data : (data.items || []);
  const light = clients.map(c => ({
    id: c.id,
    name: c.name || c.business_name || 'Unnamed',
    business_name: c.business_name || '',
    email: c.email || '',
  }));
  await setCachedClients(light);
  return light;
}

// ---------------------------------------------------------------------------
// Extension config (tier limits, feature flags, usage)
// ---------------------------------------------------------------------------

export async function getExtensionConfig() {
  return request('/extension/config');
}

// ---------------------------------------------------------------------------
// Capture
// ---------------------------------------------------------------------------

export async function captureContent(clientId, captureType, content, metadata, documentTag, imageData = null, fileUrl = null) {
  const payload = {
    client_id: clientId,
    capture_type: captureType,
    content,
    metadata,
    document_tag: documentTag,
  };
  if (imageData) payload.image_data = imageData;
  if (fileUrl) payload.file_url = fileUrl;
  return request('/extension/capture', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

// ---------------------------------------------------------------------------
// Client matching
// ---------------------------------------------------------------------------

export async function matchClient(pageData) {
  return request('/extension/match-client', {
    method: 'POST',
    body: JSON.stringify(pageData),
  });
}

// ---------------------------------------------------------------------------
// Recent captures
// ---------------------------------------------------------------------------

export async function getRecentCaptures() {
  return request('/extension/recent-captures');
}

// ---------------------------------------------------------------------------
// RAG Quick Query
// ---------------------------------------------------------------------------

export async function askQuestion(clientId, question) {
  return request(`/clients/${clientId}/rag/chat`, {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

// ---------------------------------------------------------------------------
// Monitoring rules
// ---------------------------------------------------------------------------

export async function getMonitoringRules() {
  return request('/extension/monitoring-rules');
}

export async function checkMonitoringRules(pageData) {
  return request('/extension/monitoring-rules/check', {
    method: 'POST',
    body: JSON.stringify(pageData),
  });
}

export async function createMonitoringRule(ruleData) {
  return request('/extension/monitoring-rules', {
    method: 'POST',
    body: JSON.stringify(ruleData),
  });
}

export async function updateMonitoringRule(ruleId, updates) {
  return request(`/extension/monitoring-rules/${ruleId}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  });
}

export async function deleteMonitoringRule(ruleId) {
  return request(`/extension/monitoring-rules/${ruleId}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Exports for error handling in popup
// ---------------------------------------------------------------------------

export { ERROR_CODES };
