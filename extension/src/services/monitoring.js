/**
 * Passive monitoring — checks the current page against the user's rules
 * and surfaces capture suggestions via the badge/notification.
 */

import { checkMonitoringRules } from './api.js';
import { isAuthenticated } from './auth.js';

/**
 * Check the current page against monitoring rules.
 * Called by the content script or service worker when a page loads.
 *
 * Returns array of matches or empty array.
 */
export async function checkPage(pageData) {
  const authed = await isAuthenticated();
  if (!authed) return [];

  try {
    return await checkMonitoringRules(pageData);
  } catch {
    // Non-fatal — monitoring is best-effort
    return [];
  }
}
