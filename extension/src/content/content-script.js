/**
 * Content script — runs on every page.
 *
 * Responsibilities:
 * 1. On callwen.com: detect Clerk session and relay auth token to the extension
 * 2. On all pages: respond to messages for text/metadata extraction
 * 3. Gmail: structured email extraction via parser
 * 4. Screenshot region selection
 * 5. Monitoring match banner
 */

import { isGmailPage, isEmailView, extractEmailData, formatAsDocument, getMatchHints } from '../parsers/gmail.js';

// ---------------------------------------------------------------------------
// Auth token relay (only on callwen.com)
// ---------------------------------------------------------------------------

if (window.location.hostname === 'callwen.com' || window.location.hostname === 'localhost') {
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

  checkForClerkToken();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) checkForClerkToken();
  });
}

// ---------------------------------------------------------------------------
// Site detection
// ---------------------------------------------------------------------------

function detectSite() {
  const host = window.location.hostname;
  if (host === 'mail.google.com') return 'gmail';
  if (host.includes('outlook.live.com') || host.includes('outlook.office.com')) return 'outlook';
  if (host.includes('qbo.intuit.com') || host.includes('quickbooks.intuit.com')) return 'quickbooks';
  if (host.includes('drakesoftware.com')) return 'drake';
  if (host.includes('lacerte.intuit.com')) return 'lacerte';
  if (host.includes('cs.thomsonreuters.com')) return 'ultratax';
  if (host.includes('proconnect.intuit.com')) return 'proconnect';
  return 'generic';
}

// ---------------------------------------------------------------------------
// Email extraction
// ---------------------------------------------------------------------------

function extractEmails() {
  const text = document.body?.innerText || '';
  const regex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
  const matches = text.match(regex) || [];
  return [...new Set(matches)].slice(0, 20);
}

// ---------------------------------------------------------------------------
// Company name extraction (site-specific heuristics)
// ---------------------------------------------------------------------------

function extractCompanyNames() {
  const site = detectSite();
  const names = [];

  switch (site) {
    case 'gmail': {
      // Sender name from email header
      const senderEl = document.querySelector('[data-hovercard-id]');
      if (senderEl) {
        const name = senderEl.closest('span')?.textContent?.trim();
        if (name && !name.includes('@')) names.push(name);
      }
      // Also check "From" display name
      const fromEls = document.querySelectorAll('.gD');
      fromEls.forEach(el => {
        const n = el.getAttribute('name') || el.textContent?.trim();
        if (n && !n.includes('@')) names.push(n);
      });
      break;
    }

    case 'quickbooks': {
      // Company name in QBO nav
      const companyEl = document.querySelector('[data-automation-id="company-name"]') ||
                        document.querySelector('.company-name') ||
                        document.querySelector('[class*="CompanyName"]');
      if (companyEl?.textContent?.trim()) {
        names.push(companyEl.textContent.trim());
      }
      break;
    }

    case 'outlook': {
      // Sender display name
      const senderEl = document.querySelector('[data-testid="SenderPersona"]') ||
                        document.querySelector('.lpc-hoverTarget');
      if (senderEl?.textContent?.trim()) {
        names.push(senderEl.textContent.trim());
      }
      break;
    }

    default: break;
  }

  // Generic fallbacks for all sites
  const ogSiteName = document.querySelector('meta[property="og:site_name"]')?.content;
  if (ogSiteName) names.push(ogSiteName);

  // Page title often contains the company name
  const title = document.title;
  if (title) {
    // Strip common suffixes like " - Gmail", " | Dashboard"
    const cleaned = title.replace(/\s*[-|]\s*[^-|]*$/, '').trim();
    if (cleaned && cleaned.length < 80) names.push(cleaned);
  }

  // Prominent headings
  const h1 = document.querySelector('h1');
  if (h1?.textContent?.trim() && h1.textContent.trim().length < 60) {
    names.push(h1.textContent.trim());
  }

  // Deduplicate
  return [...new Set(names)].slice(0, 10);
}

// ---------------------------------------------------------------------------
// Page metadata (full extraction)
// ---------------------------------------------------------------------------

function getPageMetadata() {
  return {
    url: window.location.href,
    title: document.title || '',
    domain: window.location.hostname,
    site_type: detectSite(),
    email_addresses: extractEmails(),
    company_names: extractCompanyNames(),
    page_text_snippet: (document.body?.innerText || '').slice(0, 2000),
  };
}

// ---------------------------------------------------------------------------
// Screenshot region selection
// ---------------------------------------------------------------------------

function startScreenshotSelection() {
  return new Promise((resolve) => {
    // Create overlay
    const overlay = document.createElement('div');
    Object.assign(overlay.style, {
      position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh',
      background: 'rgba(0, 0, 0, 0.4)', cursor: 'crosshair', zIndex: '2147483647',
    });

    // Selection box
    const selBox = document.createElement('div');
    Object.assign(selBox.style, {
      position: 'fixed', border: '2px solid #14b8a6', background: 'rgba(20, 184, 166, 0.1)',
      zIndex: '2147483647', pointerEvents: 'none', display: 'none',
    });

    // Instructions
    const hint = document.createElement('div');
    Object.assign(hint.style, {
      position: 'fixed', top: '16px', left: '50%', transform: 'translateX(-50%)',
      padding: '8px 16px', borderRadius: '8px', background: '#1a1f2e', color: '#e2e8f0',
      fontSize: '13px', fontFamily: 'system-ui, sans-serif', zIndex: '2147483647',
      boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
    });
    hint.textContent = 'Click and drag to select a region. Press Esc to cancel.';

    document.body.appendChild(overlay);
    document.body.appendChild(selBox);
    document.body.appendChild(hint);

    let startX = 0, startY = 0, dragging = false;

    const cleanup = () => {
      overlay.remove();
      selBox.remove();
      hint.remove();
      document.removeEventListener('keydown', onKey);
    };

    const onKey = (e) => {
      if (e.key === 'Escape') {
        cleanup();
        resolve(null);
      }
    };
    document.addEventListener('keydown', onKey);

    overlay.addEventListener('mousedown', (e) => {
      startX = e.clientX;
      startY = e.clientY;
      dragging = true;
      selBox.style.display = 'block';
      selBox.style.left = `${startX}px`;
      selBox.style.top = `${startY}px`;
      selBox.style.width = '0';
      selBox.style.height = '0';
    });

    overlay.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const x = Math.min(startX, e.clientX);
      const y = Math.min(startY, e.clientY);
      const w = Math.abs(e.clientX - startX);
      const h = Math.abs(e.clientY - startY);
      Object.assign(selBox.style, {
        left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px`,
      });
    });

    overlay.addEventListener('mouseup', (e) => {
      if (!dragging) return;
      dragging = false;

      const rect = {
        x: Math.min(startX, e.clientX),
        y: Math.min(startY, e.clientY),
        width: Math.abs(e.clientX - startX),
        height: Math.abs(e.clientY - startY),
      };

      cleanup();

      // Minimum selection size (10x10)
      if (rect.width < 10 || rect.height < 10) {
        resolve(null);
        return;
      }

      // Include devicePixelRatio for retina displays
      resolve({
        x: rect.x * window.devicePixelRatio,
        y: rect.y * window.devicePixelRatio,
        width: rect.width * window.devicePixelRatio,
        height: rect.height * window.devicePixelRatio,
        dpr: window.devicePixelRatio,
      });
    });
  });
}

// ---------------------------------------------------------------------------
// Monitoring match banner
// ---------------------------------------------------------------------------

function showMonitoringBanner(clientName, ruleName) {
  // Remove any existing banner
  const existing = document.getElementById('callwen-monitoring-banner');
  if (existing) existing.remove();

  const banner = document.createElement('div');
  banner.id = 'callwen-monitoring-banner';
  Object.assign(banner.style, {
    position: 'fixed', top: '0', left: '0', right: '0', zIndex: '2147483646',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px',
    padding: '10px 16px', background: '#1a1f2e', borderBottom: '1px solid #2d3748',
    fontFamily: 'system-ui, sans-serif', fontSize: '13px', color: '#e2e8f0',
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
    transition: 'transform 0.3s ease', transform: 'translateY(-100%)',
  });

  const text = document.createElement('span');
  text.textContent = `\u{1F4CE} Callwen: This page may be related to ${clientName}. Capture it?`;

  const captureBtn = document.createElement('button');
  Object.assign(captureBtn.style, {
    padding: '4px 12px', borderRadius: '4px', border: 'none',
    background: '#14b8a6', color: '#0f1419', fontSize: '12px',
    fontWeight: '600', cursor: 'pointer',
  });
  captureBtn.textContent = 'Capture';

  const dismissBtn = document.createElement('button');
  Object.assign(dismissBtn.style, {
    padding: '4px 12px', borderRadius: '4px', border: '1px solid #2d3748',
    background: 'transparent', color: '#94a3b8', fontSize: '12px',
    cursor: 'pointer',
  });
  dismissBtn.textContent = 'Dismiss';

  banner.appendChild(text);
  banner.appendChild(captureBtn);
  banner.appendChild(dismissBtn);
  document.body.appendChild(banner);

  // Slide in
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      banner.style.transform = 'translateY(0)';
    });
  });

  const removeBanner = () => {
    banner.style.transform = 'translateY(-100%)';
    setTimeout(() => banner.remove(), 300);
  };

  captureBtn.addEventListener('click', () => {
    removeBanner();
    // Tell the service worker to open the popup
    chrome.runtime.sendMessage({ type: 'OPEN_POPUP_FOR_CAPTURE' });
  });

  dismissBtn.addEventListener('click', removeBanner);

  // Auto-dismiss after 10 seconds
  setTimeout(() => {
    if (document.getElementById('callwen-monitoring-banner')) {
      removeBanner();
    }
  }, 10000);
}

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case 'GET_PAGE_METADATA':
      sendResponse(getPageMetadata());
      return false;

    case 'GET_SELECTED_TEXT':
      sendResponse({ text: window.getSelection().toString() });
      return false;

    case 'GET_PAGE_TEXT':
      sendResponse({
        text: (document.body?.innerText || '').slice(0, 500000),
        title: document.title || '',
        url: window.location.href,
      });
      return false;

    case 'GET_SITE_TYPE':
      sendResponse({ site_type: detectSite() });
      return false;

    case 'GET_PARSED_CONTENT': {
      const site = detectSite();
      if (site === 'gmail' && isGmailPage() && isEmailView()) {
        const emailData = extractEmailData();
        const content = formatAsDocument(emailData);
        const metadata = getMatchHints(emailData);
        sendResponse({
          parsed: true,
          content,
          metadata,
          email_data: emailData,
          capture_type: 'text_selection',
          document_tag: 'correspondence',
        });
      } else {
        sendResponse({ parsed: false });
      }
      return false;
    }

    case 'START_SCREENSHOT_SELECTION':
      startScreenshotSelection().then(region => {
        sendResponse({ region });
      });
      return true; // async response

    case 'SHOW_MONITORING_MATCH':
      showMonitoringBanner(message.client_name, message.rule_name);
      sendResponse({ ok: true });
      return false;

    default:
      return false;
  }
});
