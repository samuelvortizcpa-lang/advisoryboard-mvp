/**
 * Content script — runs on every page.
 *
 * Responsibilities:
 * 1. On callwen.com: detect Clerk session and relay auth token to the extension
 * 2. On all pages: extract page metadata for monitoring rule checks
 */

// ---------------------------------------------------------------------------
// Auth token relay (only on callwen.com)
// ---------------------------------------------------------------------------

if (window.location.hostname === 'callwen.com' || window.location.hostname === 'localhost') {
  // Look for Clerk session token in cookies
  const checkForClerkToken = () => {
    const cookies = document.cookie.split(';').map(c => c.trim());
    const sessionCookie = cookies.find(c => c.startsWith('__session='));
    if (sessionCookie) {
      const token = sessionCookie.split('=')[1];
      if (token) {
        chrome.runtime.sendMessage({ type: 'AUTH_TOKEN', token });
      }
    }
  };

  // Check immediately and on visibility change (tab switch back)
  checkForClerkToken();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) checkForClerkToken();
  });
}

// ---------------------------------------------------------------------------
// Page metadata extraction (for monitoring rules)
// ---------------------------------------------------------------------------

function getPageMetadata() {
  // Extract email addresses visible on the page
  const textContent = document.body?.innerText || '';
  const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
  const emails = [...new Set(textContent.match(emailRegex) || [])].slice(0, 20);

  return {
    url: window.location.href,
    domain: window.location.hostname,
    email_addresses: emails,
    page_text_snippet: textContent.slice(0, 2000),
  };
}

// Respond to metadata requests from the service worker
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_PAGE_METADATA') {
    sendResponse(getPageMetadata());
    return false;
  }
});
