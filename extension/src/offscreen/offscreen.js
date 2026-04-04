/**
 * Offscreen document for silent token refresh.
 *
 * The service worker sends { type: 'REFRESH_TOKEN' } and this script loads
 * the auth callback page in a hidden iframe, extracts the JWT, and relays it
 * back via chrome.runtime.sendMessage.
 */

const TIMEOUT_MS = 8_000;
const POLL_INTERVAL_MS = 300;

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'REFRESH_TOKEN') {
    refreshToken();
  }
});

async function refreshToken() {
  const frame = document.getElementById('auth-frame');
  let settled = false;

  function finish(token, error) {
    if (settled) return;
    settled = true;
    frame.src = 'about:blank';
    chrome.runtime.sendMessage({
      type: 'REFRESH_TOKEN_RESULT',
      token: token || null,
      error: error || null,
    });
  }

  // Listen for postMessage from the iframe (the auth callback page posts the token)
  window.addEventListener('message', (event) => {
    if (settled) return;
    if (event.data && event.data.type === 'CALLWEN_TOKEN' && event.data.token) {
      finish(event.data.token);
    }
  });

  // Timeout fallback
  const timer = setTimeout(() => {
    finish(null, 'timeout');
  }, TIMEOUT_MS);

  // Also poll the iframe URL hash as a fallback — the auth callback page
  // puts the token in the URL as ?token=JWT via replaceState.
  const poller = setInterval(() => {
    if (settled) {
      clearInterval(poller);
      return;
    }
    try {
      const url = frame.contentWindow?.location?.href;
      if (url) {
        const match = url.match(/[?&]token=([^&]+)/);
        if (match) {
          clearInterval(poller);
          clearTimeout(timer);
          finish(decodeURIComponent(match[1]));
        }
      }
    } catch {
      // Cross-origin — expected, postMessage path will handle it
    }
  }, POLL_INTERVAL_MS);

  // Load the auth callback page in the iframe
  frame.src = 'https://callwen.com/extension-auth-callback?refresh=true&offscreen=true';
}
