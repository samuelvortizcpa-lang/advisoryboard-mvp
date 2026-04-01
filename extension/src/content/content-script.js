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
import {
  isQuickBooksPage, detectQBOPage, extractReportData, extractTransactionData,
  getMatchHints as getQBOMatchHints, formatAsDocument as formatQBODocument,
} from '../parsers/quickbooks.js';
import {
  isTaxSoftwarePage, detectTaxSoftware, extractTaxData,
  formatAsDocument as formatTaxDocument, getMatchHints as getTaxMatchHints,
} from '../parsers/tax-software.js';

// ---------------------------------------------------------------------------
// Auth callback detection — relay JWT from /extension-auth-callback to service worker
// ---------------------------------------------------------------------------

(function detectAuthCallback() {
  if (!window.location.pathname.startsWith('/extension-auth-callback')) return;

  let tokenSent = false;

  function checkAndRelayToken() {
    if (tokenSent) return true;
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (!token) return false;

    tokenSent = true;
    console.log('[Callwen] Relaying auth token to service worker');
    chrome.runtime.sendMessage(
      { type: 'AUTH_TOKEN_FROM_PAGE', token },
      (response) => {
        console.log('[Callwen] Service worker response:', response);
      }
    );
    return true;
  }

  // Immediate check (content script may load after the token is already in URL)
  if (checkAndRelayToken()) return;

  // Poll for token — the page uses replaceState to update the URL without
  // reloading, so we need to keep checking until the token appears.
  const poller = setInterval(() => {
    if (checkAndRelayToken()) clearInterval(poller);
  }, 300);

  // Give up after 30 seconds
  setTimeout(() => clearInterval(poller), 30000);
})();

// ---------------------------------------------------------------------------
// Auth token relay (only on callwen.com) — Clerk cookie passthrough
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
  if (host.includes('drakesoftware.com') || host.includes('drakecpe.com')) return 'drake';
  if (host.includes('lacerte.intuit.com')) return 'lacerte';
  if (host.includes('cs.thomsonreuters.com')) return 'ultratax';
  if (host.includes('proconnect.intuit.com')) return 'proconnect';
  if (host.includes('proseries.intuit.com')) return 'proseries';
  if (host.includes('pro.taxact.com')) return 'taxact_pro';
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
    const Z = '2147483647';
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Container for all screenshot UI elements
    const container = document.createElement('div');
    container.id = 'callwen-screenshot-overlay';
    Object.assign(container.style, {
      position: 'fixed', top: '0', left: '0', width: '100vw', height: '100vh',
      zIndex: Z, cursor: 'crosshair',
    });

    // Dim overlay (4 divs surrounding the cutout — top, bottom, left, right)
    const dimColor = 'rgba(0, 0, 0, 0.35)';
    const dims = ['top', 'bottom', 'left', 'right'].map(id => {
      const d = document.createElement('div');
      d.dataset.pos = id;
      Object.assign(d.style, {
        position: 'absolute', background: dimColor, transition: 'none',
      });
      return d;
    });
    // Initially: full overlay dim (no cutout)
    Object.assign(dims[0].style, { top: '0', left: '0', width: '100%', height: '100%' }); // top = full
    Object.assign(dims[1].style, { top: '0', left: '0', width: '0', height: '0' }); // bottom hidden
    Object.assign(dims[2].style, { top: '0', left: '0', width: '0', height: '0' }); // left hidden
    Object.assign(dims[3].style, { top: '0', left: '0', width: '0', height: '0' }); // right hidden
    dims.forEach(d => container.appendChild(d));

    // Selection border
    const selBorder = document.createElement('div');
    Object.assign(selBorder.style, {
      position: 'absolute', border: '1.5px solid rgba(255,255,255,0.8)',
      boxShadow: '0 0 0 1px rgba(0,0,0,0.3), inset 0 0 0 1px rgba(0,0,0,0.1)',
      borderRadius: '2px', pointerEvents: 'none', display: 'none',
    });
    container.appendChild(selBorder);

    // Dimension indicator
    const dimLabel = document.createElement('div');
    Object.assign(dimLabel.style, {
      position: 'absolute', padding: '2px 8px', borderRadius: '4px',
      background: 'rgba(0,0,0,0.75)', color: '#fff', fontSize: '11px',
      fontFamily: 'system-ui, -apple-system, sans-serif', pointerEvents: 'none',
      display: 'none', whiteSpace: 'nowrap',
    });
    container.appendChild(dimLabel);

    // Instructions hint
    const hint = document.createElement('div');
    Object.assign(hint.style, {
      position: 'absolute', top: '20px', left: '50%', transform: 'translateX(-50%)',
      padding: '8px 18px', borderRadius: '20px', background: 'rgba(0,0,0,0.7)',
      backdropFilter: 'blur(8px)', WebkitBackdropFilter: 'blur(8px)',
      color: '#f1f5f9', fontSize: '13px', fontFamily: 'system-ui, -apple-system, sans-serif',
      pointerEvents: 'none', transition: 'opacity 0.3s',
      boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
    });
    hint.textContent = 'Click and drag to select a region \u00B7 Esc to cancel';
    container.appendChild(hint);

    // Auto-fade hint after 3 seconds
    const hintTimer = setTimeout(() => { hint.style.opacity = '0'; }, 3000);

    document.body.appendChild(container);

    let startX = 0, startY = 0, dragging = false;

    function updateDims(x, y, w, h) {
      // Four-div cutout: top strip, bottom strip, left column, right column
      // Top: full width, from top to selection top
      Object.assign(dims[0].style, { top: '0', left: '0', width: `${vw}px`, height: `${y}px` });
      // Bottom: full width, from selection bottom to viewport bottom
      Object.assign(dims[1].style, { top: `${y + h}px`, left: '0', width: `${vw}px`, height: `${vh - y - h}px` });
      // Left: from selection top to selection bottom, left edge to selection left
      Object.assign(dims[2].style, { top: `${y}px`, left: '0', width: `${x}px`, height: `${h}px` });
      // Right: from selection top to selection bottom, selection right to viewport right
      Object.assign(dims[3].style, { top: `${y}px`, left: `${x + w}px`, width: `${vw - x - w}px`, height: `${h}px` });
    }

    const cleanup = () => {
      clearTimeout(hintTimer);
      container.remove();
      document.removeEventListener('keydown', onKey);
    };

    const onKey = (e) => {
      if (e.key === 'Escape') { cleanup(); resolve(null); }
    };
    document.addEventListener('keydown', onKey);

    // Right-click cancels
    container.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      cleanup();
      resolve(null);
    });

    container.addEventListener('mousedown', (e) => {
      if (e.button !== 0) return; // left click only
      startX = e.clientX;
      startY = e.clientY;
      dragging = true;
      hint.style.opacity = '0';
      selBorder.style.display = 'block';
      dimLabel.style.display = 'block';
    });

    container.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      const x = Math.min(startX, e.clientX);
      const y = Math.min(startY, e.clientY);
      const w = Math.abs(e.clientX - startX);
      const h = Math.abs(e.clientY - startY);

      Object.assign(selBorder.style, {
        left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px`,
      });

      updateDims(x, y, w, h);

      // Dimension label positioned below bottom-right corner
      dimLabel.textContent = `${Math.round(w * devicePixelRatio)} \u00D7 ${Math.round(h * devicePixelRatio)}`;
      const labelX = Math.min(x + w + 4, vw - 80);
      const labelY = Math.min(y + h + 4, vh - 24);
      Object.assign(dimLabel.style, { left: `${labelX}px`, top: `${labelY}px` });
    });

    container.addEventListener('mouseup', (e) => {
      if (!dragging) return;
      dragging = false;

      const x = Math.min(startX, e.clientX);
      const y = Math.min(startY, e.clientY);
      const w = Math.abs(e.clientX - startX);
      const h = Math.abs(e.clientY - startY);

      // Minimum selection size
      if (w < 10 || h < 10) {
        // Reset to full dim, let user try again
        Object.assign(dims[0].style, { top: '0', left: '0', width: '100%', height: '100%' });
        dims.slice(1).forEach(d => Object.assign(d.style, { width: '0', height: '0' }));
        selBorder.style.display = 'none';
        dimLabel.style.display = 'none';
        // Show brief "drag to select" hint
        hint.textContent = 'Drag to select a region';
        hint.style.opacity = '1';
        setTimeout(() => { hint.style.opacity = '0'; }, 2000);
        return;
      }

      // Brief gold flash on the border
      selBorder.style.borderColor = '#c9944a';
      selBorder.style.boxShadow = '0 0 0 2px rgba(201,148,74,0.4)';

      setTimeout(() => {
        cleanup();
        const dpr = window.devicePixelRatio || 1;
        resolve({
          x: x * dpr,
          y: y * dpr,
          width: w * dpr,
          height: h * dpr,
          dpr,
        });
      }, 150);
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
    background: '#c9944a', color: '#ffffff', fontSize: '12px',
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

      // Gmail email parser
      if (site === 'gmail' && isGmailPage() && isEmailView()) {
        const emailData = extractEmailData();
        const content = formatAsDocument(emailData);
        const metadata = getMatchHints(emailData);
        sendResponse({
          parsed: true,
          parser: 'gmail',
          content,
          metadata,
          email_data: emailData,
          capture_type: 'text_selection',
          document_tag: 'correspondence',
        });
        return false;
      }

      // QuickBooks Online parser
      if (site === 'quickbooks' && isQuickBooksPage()) {
        const pageType = detectQBOPage();
        if (pageType === 'report') {
          const reportData = extractReportData();
          const content = formatQBODocument('report', reportData);
          sendResponse({
            parsed: true,
            parser: 'quickbooks',
            qbo_page_type: pageType,
            content,
            metadata: getQBOMatchHints(),
            qbo_data: reportData,
            capture_type: 'full_page',
            document_tag: 'financial_statement',
          });
          return false;
        }
        if (pageType === 'transaction') {
          const txnData = extractTransactionData();
          const content = formatQBODocument('transaction', txnData);
          sendResponse({
            parsed: true,
            parser: 'quickbooks',
            qbo_page_type: pageType,
            content,
            metadata: getQBOMatchHints(),
            qbo_data: txnData,
            capture_type: 'full_page',
            document_tag: 'financial_statement',
          });
          return false;
        }
        // dashboard, customer_list, unknown — fall through to generic
      }

      // Tax software parser
      if (isTaxSoftwarePage()) {
        const softwareName = detectTaxSoftware();
        const taxData = extractTaxData();
        const content = formatTaxDocument(softwareName, taxData);
        sendResponse({
          parsed: true,
          parser: 'tax_software',
          content,
          metadata: getTaxMatchHints(taxData),
          tax_data: taxData,
          software_name: softwareName,
          capture_type: 'full_page',
          document_tag: 'tax_document',
        });
        return false;
      }

      sendResponse({ parsed: false });
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

    case 'SEARCH_PAGE_TEXT': {
      const pageText = (document.body?.innerText || '').toLowerCase();
      const searchPattern = (message.pattern || '').toLowerCase();
      sendResponse({ found: searchPattern && pageText.includes(searchPattern) });
      return false;
    }

    default:
      return false;
  }
});
