/**
 * API client for Callwen backend.
 *
 * All extension API calls go through here so auth headers and error handling
 * are consistent.
 */

import { CONFIG } from '../utils/config.js';
import { getAuthToken } from '../utils/storage.js';

async function request(path, options = {}) {
  const token = await getAuthToken();
  if (!token) {
    throw new Error('Not authenticated. Please sign in to Callwen.');
  }

  const url = `${CONFIG.API_BASE_URL}/api${path}`;
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    ...options.headers,
  };

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // non-JSON error response
    }
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    err.status = response.status;
    throw err;
  }

  if (response.status === 204) return null;
  return response.json();
}

// ---------------------------------------------------------------------------
// Extension endpoints
// ---------------------------------------------------------------------------

export async function getExtensionConfig() {
  return request('/extension/config');
}

export async function captureContent(payload) {
  return request('/extension/capture', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function matchClient(pageData) {
  return request('/extension/match-client', {
    method: 'POST',
    body: JSON.stringify(pageData),
  });
}

export async function getRecentCaptures() {
  return request('/extension/recent-captures');
}

// ---------------------------------------------------------------------------
// Monitoring rules
// ---------------------------------------------------------------------------

export async function getMonitoringRules() {
  return request('/extension/monitoring-rules');
}

export async function createMonitoringRule(rule) {
  return request('/extension/monitoring-rules', {
    method: 'POST',
    body: JSON.stringify(rule),
  });
}

export async function updateMonitoringRule(id, updates) {
  return request(`/extension/monitoring-rules/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  });
}

export async function deleteMonitoringRule(id) {
  return request(`/extension/monitoring-rules/${id}`, {
    method: 'DELETE',
  });
}

export async function checkMonitoringRules(pageData) {
  return request('/extension/monitoring-rules/check', {
    method: 'POST',
    body: JSON.stringify(pageData),
  });
}

// ---------------------------------------------------------------------------
// Client list (for the popup picker)
// ---------------------------------------------------------------------------

export async function getClients() {
  return request('/clients');
}
