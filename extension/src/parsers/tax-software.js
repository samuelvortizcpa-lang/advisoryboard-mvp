/**
 * Tax software parsers — Drake, Lacerte, UltraTax.
 *
 * These are primarily web-based portals. Extract client name,
 * EIN/SSN context, and page content when on recognized domains.
 */

const TAX_DOMAINS = [
  'drakesoftware.com',
  'lacerte.intuit.com',
  'cs.thomsonreuters.com',  // UltraTax CS
  'proconnect.intuit.com',  // ProConnect Tax
];

export function isTaxSoftwarePage() {
  return TAX_DOMAINS.some(d => window.location.hostname.includes(d));
}

export function parseTaxSoftwarePage() {
  const bodyText = document.body?.innerText?.slice(0, 10000) || '';
  const title = document.title || '';

  return {
    type: 'tax_software',
    page_title: title,
    content: bodyText,
    url: window.location.href,
    domain: window.location.hostname,
  };
}
