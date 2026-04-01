/**
 * QuickBooks Online parser.
 *
 * Detects QBO pages and extracts client/transaction context.
 */

export function isQuickBooksPage() {
  return window.location.hostname.includes('qbo.intuit.com') ||
    window.location.hostname.includes('quickbooks.intuit.com');
}

export function parseQuickBooksPage() {
  const title = document.title || '';
  const bodyText = document.body?.innerText?.slice(0, 10000) || '';

  return {
    type: 'quickbooks',
    page_title: title,
    content: bodyText,
    url: window.location.href,
  };
}
