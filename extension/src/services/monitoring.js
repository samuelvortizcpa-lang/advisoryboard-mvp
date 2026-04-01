/**
 * Passive monitoring engine.
 *
 * Caches active monitoring rules in session storage and checks pages
 * against them on navigation. Shows non-intrusive notifications when
 * a page matches a rule.
 */

import { getMonitoringRules } from './api.js';
import { isAuthenticated } from './auth.js';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RULES_CACHE_KEY = 'monitoring_rules_cache';
const RULES_CACHE_TS_KEY = 'monitoring_rules_cache_ts';
const NOTIFIED_KEY = 'monitoring_notified';
const MONITORING_PREFS_KEY = 'callwen_monitoring_prefs';
const RULES_REFRESH_MS = 5 * 60 * 1000; // 5 minutes
const CHECK_COOLDOWN_MS = 30 * 1000; // 30s per URL

// Track last-checked URLs to rate-limit (in-memory, resets on SW restart)
const lastChecked = new Map(); // url → timestamp

// ---------------------------------------------------------------------------
// Rule loading & caching
// ---------------------------------------------------------------------------

/**
 * Fetch active monitoring rules from the API and cache in session storage.
 * Returns the rules array. Uses cached version if fresh enough.
 */
export async function loadRules(forceRefresh = false) {
  if (!forceRefresh) {
    try {
      const cached = await chrome.storage.session.get([RULES_CACHE_KEY, RULES_CACHE_TS_KEY]);
      const ts = cached[RULES_CACHE_TS_KEY] || 0;
      if (cached[RULES_CACHE_KEY] && Date.now() - ts < RULES_REFRESH_MS) {
        return cached[RULES_CACHE_KEY];
      }
    } catch { /* session storage unavailable */ }
  }

  try {
    const authed = await isAuthenticated();
    if (!authed) return [];

    const result = await getMonitoringRules();
    const rules = Array.isArray(result) ? result : (result?.rules || []);
    // Only cache active rules
    const active = rules.filter(r => r.is_active !== false);

    await chrome.storage.session.set({
      [RULES_CACHE_KEY]: active,
      [RULES_CACHE_TS_KEY]: Date.now(),
    });

    return active;
  } catch {
    // Fallback to cached if API fails
    try {
      const cached = await chrome.storage.session.get(RULES_CACHE_KEY);
      return cached[RULES_CACHE_KEY] || [];
    } catch {
      return [];
    }
  }
}

/**
 * Invalidate the rules cache. Called when the user modifies rules in the popup.
 */
export async function invalidateRulesCache() {
  await chrome.storage.session.remove([RULES_CACHE_KEY, RULES_CACHE_TS_KEY]);
}

// ---------------------------------------------------------------------------
// Page checking
// ---------------------------------------------------------------------------

/**
 * Check if a page matches any monitoring rules.
 *
 * @param {number} tabId
 * @param {string} url
 * @param {string} domain
 * @returns {Array} Matching rules with client info
 */
export async function checkPage(tabId, url, domain) {
  // Rate limit: skip if checked this URL recently
  const now = Date.now();
  const lastTime = lastChecked.get(url);
  if (lastTime && now - lastTime < CHECK_COOLDOWN_MS) return [];
  lastChecked.set(url, now);

  // Clean old entries
  if (lastChecked.size > 100) {
    for (const [k, v] of lastChecked) {
      if (now - v > CHECK_COOLDOWN_MS * 2) lastChecked.delete(k);
    }
  }

  const rules = await loadRules();
  if (!rules.length) return [];

  const matches = [];

  for (const rule of rules) {
    const ruleType = rule.rule_type || rule.type;
    const pattern = (rule.pattern || '').toLowerCase();

    if (!pattern) continue;

    let matched = false;

    switch (ruleType) {
      case 'domain':
        // Exact match or subdomain match
        matched = domain === pattern ||
                  domain.endsWith('.' + pattern);
        break;

      case 'url_contains':
        matched = url.toLowerCase().includes(pattern);
        break;

      case 'url_pattern': {
        // Convert simple wildcards to regex
        try {
          const escaped = pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&');
          const regex = new RegExp(escaped.replace(/\*/g, '.*'), 'i');
          matched = regex.test(url);
        } catch {
          // Invalid pattern, try simple contains
          matched = url.toLowerCase().includes(pattern);
        }
        break;
      }

      case 'page_title': {
        try {
          const tab = await chrome.tabs.get(tabId);
          matched = (tab.title || '').toLowerCase().includes(pattern);
        } catch {
          matched = false;
        }
        break;
      }

      case 'page_content': {
        // Ask content script to search page text
        try {
          const response = await chrome.tabs.sendMessage(tabId, {
            type: 'SEARCH_PAGE_TEXT',
            pattern,
          });
          matched = response?.found === true;
        } catch {
          matched = false;
        }
        break;
      }

      case 'email_from':
      case 'email_sender':
        // Checked via checkEmailSender() when parsers extract email data
        continue;

      default:
        continue;
    }

    if (matched) {
      matches.push({
        rule_id: rule.id,
        rule_name: rule.name || 'Unnamed rule',
        rule_type: ruleType,
        pattern: rule.pattern,
        client_id: rule.client_id,
        client_name: rule.client_name || 'Unknown',
      });
    }
  }

  return matches;
}

/**
 * Check extracted email addresses against email_sender rules.
 *
 * @param {string[]} emailAddresses
 * @returns {Array} Matching rules
 */
export async function checkEmailSender(emailAddresses) {
  if (!emailAddresses?.length) return [];

  const rules = await loadRules();
  if (!rules.length) return [];

  const matches = [];
  const lowerEmails = emailAddresses.map(e => e.toLowerCase());

  for (const rule of rules) {
    const ruleType = rule.rule_type || rule.type;
    if (ruleType !== 'email_from' && ruleType !== 'email_sender') continue;

    const pattern = (rule.pattern || '').toLowerCase();
    if (!pattern) continue;

    // Match exact email or domain part
    const matched = lowerEmails.some(email =>
      email === pattern || email.endsWith('@' + pattern)
    );

    if (matched) {
      matches.push({
        rule_id: rule.id,
        rule_name: rule.name || 'Unnamed rule',
        rule_type: ruleType,
        pattern: rule.pattern,
        client_id: rule.client_id,
        client_name: rule.client_name || 'Unknown',
      });
    }
  }

  return matches;
}

// ---------------------------------------------------------------------------
// Notification display
// ---------------------------------------------------------------------------

/**
 * Show a non-intrusive notification for matched rules.
 *
 * First tries the content script banner, falls back to Chrome notification.
 * Deduplicates by URL + rule combo per session.
 */
export async function showMatchNotification(tabId, url, matches) {
  if (!matches.length) return;

  const topMatch = matches[0];

  // Deduplicate: don't re-notify for same URL + rule in this session
  const notifKey = `${url}::${topMatch.rule_id}`;
  try {
    const stored = await chrome.storage.session.get(NOTIFIED_KEY);
    const notified = stored[NOTIFIED_KEY] || {};
    if (notified[notifKey]) return;

    // Mark as notified
    notified[notifKey] = Date.now();

    // Trim old entries (keep last 50)
    const entries = Object.entries(notified);
    if (entries.length > 50) {
      entries.sort((a, b) => b[1] - a[1]);
      await chrome.storage.session.set({ [NOTIFIED_KEY]: Object.fromEntries(entries.slice(0, 50)) });
    } else {
      await chrome.storage.session.set({ [NOTIFIED_KEY]: notified });
    }
  } catch { /* session storage unavailable */ }

  // Try content script banner first
  let bannerShown = false;
  try {
    await chrome.tabs.sendMessage(tabId, {
      type: 'SHOW_MONITORING_MATCH',
      client_name: topMatch.client_name,
      client_id: topMatch.client_id,
      rule_name: topMatch.rule_name,
    });
    bannerShown = true;
  } catch { /* content script not available */ }

  // Chrome notification as backup
  if (!bannerShown) {
    try {
      chrome.notifications.create(`monitoring-${tabId}-${Date.now()}`, {
        type: 'basic',
        iconUrl: 'assets/icon-128.png',
        title: 'Callwen',
        message: `This page may be related to ${topMatch.client_name}`,
        priority: 1,
      });
    } catch { /* notifications API unavailable */ }
  }
}

// ---------------------------------------------------------------------------
// Monitoring preferences
// ---------------------------------------------------------------------------

/**
 * Get monitoring preferences from local storage.
 */
export async function getMonitoringPrefs() {
  const result = await chrome.storage.local.get(MONITORING_PREFS_KEY);
  return result[MONITORING_PREFS_KEY] || {
    enabled: true,
    muted_until: 0,
  };
}

/**
 * Update monitoring preferences.
 */
export async function setMonitoringPrefs(prefs) {
  const current = await getMonitoringPrefs();
  const updated = { ...current, ...prefs };
  await chrome.storage.local.set({ [MONITORING_PREFS_KEY]: updated });
  return updated;
}

/**
 * Check if monitoring is currently active (enabled and not muted).
 */
export async function isMonitoringActive() {
  const prefs = await getMonitoringPrefs();
  if (!prefs.enabled) return false;
  if (prefs.muted_until && Date.now() < prefs.muted_until) return false;
  return true;
}
