/**
 * Generic page parser — fallback for any webpage not specifically handled.
 *
 * Extracts clean page content by stripping navigation, footers, cookie
 * banners, and other UI noise. Also extracts structured metadata.
 */

/**
 * Extract the main page content, stripping common noise elements.
 */
export function extractPageContent() {
  const body = document.body;
  if (!body) return '';

  // Try to find the main content area first
  const main = document.querySelector(
    '[role="main"], main, article, .main-content, #main-content, ' +
    '.content, #content, .post-content, .article-content, .entry-content'
  );

  const source = main || body;
  const clone = source.cloneNode(true);

  // Remove common noise elements
  const noiseSelectors = [
    'nav', 'footer', 'header',
    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
    '[class*="sidebar"]', '[class*="Sidebar"]',
    '[class*="nav-"]', '[class*="Nav"]', '[class*="navbar"]',
    '[class*="footer"]', '[class*="Footer"]',
    '[class*="menu"]', '[class*="Menu"]',
    '[class*="toolbar"]', '[class*="Toolbar"]',
    '[class*="cookie"]', '[class*="Cookie"]', '[class*="consent"]',
    '[class*="banner"]', '[class*="popup"]', '[class*="modal"]',
    '[class*="advertisement"]', '[class*="ad-"]', '[class*="ads-"]',
    '[class*="social-share"]', '[class*="share-"]',
    '[class*="comment"]', '[class*="Comment"]',
    'script', 'style', 'noscript', 'iframe',
  ];

  noiseSelectors.forEach(sel => {
    try {
      clone.querySelectorAll(sel).forEach(el => el.remove());
    } catch { /* invalid selector on some pages */ }
  });

  let text = clone.innerText || '';

  // Collapse excessive whitespace
  text = text
    .replace(/\t/g, ' ')
    .replace(/ {3,}/g, '  ')
    .replace(/\n{4,}/g, '\n\n\n')
    .trim();

  return text.slice(0, 500000);
}

/**
 * Extract structured metadata from the page.
 */
export function extractMetadata() {
  const meta = {
    title: document.title || '',
    url: window.location.href,
    domain: window.location.hostname,
    description: '',
    author: '',
    published_date: '',
  };

  // Meta description
  const descEl = document.querySelector(
    'meta[name="description"], meta[property="og:description"]'
  );
  if (descEl) meta.description = descEl.content || '';

  // Author
  const authorEl = document.querySelector(
    'meta[name="author"], meta[property="article:author"]'
  );
  if (authorEl) meta.author = authorEl.content || '';

  // Published date
  const dateEl = document.querySelector(
    'meta[property="article:published_time"], meta[name="date"], ' +
    'meta[name="publish-date"], meta[property="og:article:published_time"]'
  );
  if (dateEl) {
    meta.published_date = dateEl.content || '';
  } else {
    // Fallback: look for <time> elements
    const timeEl = document.querySelector('time[datetime]');
    if (timeEl) meta.published_date = timeEl.getAttribute('datetime') || '';
  }

  return meta;
}

/**
 * Format extracted content and metadata into a clean text document.
 */
export function formatAsDocument(content, metadata) {
  const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  const lines = [];

  lines.push('Web Page Capture');
  if (metadata.title) lines.push(`Title: ${metadata.title}`);
  lines.push(`URL: ${metadata.url}`);
  if (metadata.author) lines.push(`Author: ${metadata.author}`);
  if (metadata.published_date) lines.push(`Published: ${metadata.published_date}`);
  lines.push(`Captured: ${timestamp}`);
  lines.push('');
  lines.push(content);

  return lines.join('\n');
}
