/**
 * Tax software parser — Drake, Lacerte, UltraTax, ProSeries, TaxAct Pro.
 *
 * Best-effort extraction from web-based tax prep portals. Focuses on
 * common patterns (client name, form type, tax year) and critically
 * sanitizes PII (SSN, EIN, bank accounts) before capture.
 */

const TAX_DOMAINS = {
  'drakesoftware.com': 'Drake Software',
  'drakecpe.com': 'Drake Software',
  'lacerte.intuit.com': 'Lacerte',
  'cs.thomsonreuters.com': 'UltraTax CS',
  'proconnect.intuit.com': 'ProConnect Tax',
  'proseries.intuit.com': 'ProSeries',
  'pro.taxact.com': 'TaxAct Professional',
};

/**
 * Check if the current page is a known tax software site.
 */
export function isTaxSoftwarePage() {
  return detectTaxSoftware() !== 'unknown';
}

/**
 * Identify the tax software from the URL/domain.
 */
export function detectTaxSoftware() {
  const host = window.location.hostname.toLowerCase();
  for (const [domain, name] of Object.entries(TAX_DOMAINS)) {
    if (host.includes(domain)) return name;
  }
  return 'unknown';
}

/**
 * Best-effort extraction of tax data from the current page.
 */
export function extractTaxData() {
  const data = {
    client_name: '',
    form_type: '',
    tax_year: '',
    raw_content: '',
    has_sensitive_data: false,
  };

  // Get the main content area, stripping nav/sidebar/footer
  const mainContent = getMainContent();
  data.raw_content = mainContent;

  // Client name — look for prominent display patterns
  data.client_name = findClientName();

  // Form type — look for IRS form identifiers
  data.form_type = findFormType(mainContent);

  // Tax year — look for 4-digit years in tax context
  data.tax_year = findTaxYear(mainContent);

  // Check for sensitive data presence
  data.has_sensitive_data = hasSensitiveData(mainContent);

  return data;
}

/**
 * Find the client/taxpayer name on the page.
 */
function findClientName() {
  // Common selectors across tax software UIs
  const selectors = [
    '[data-testid*="client-name"]', '[data-testid*="taxpayer"]',
    '[class*="clientName"]', '[class*="ClientName"]', '[class*="client-name"]',
    '[class*="taxpayerName"]', '[class*="TaxpayerName"]',
    '[id*="clientName"]', '[id*="taxpayerName"]',
    // Header areas often display the client
    '.client-header', '.taxpayer-header', '.return-header',
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    const text = el?.textContent?.trim();
    if (text && text.length > 1 && text.length < 100) return text;
  }

  // Heuristic: look for a name pattern near "Client:" or "Taxpayer:" labels
  const labels = document.querySelectorAll('label, th, dt, .label');
  for (const label of labels) {
    const text = label.textContent?.trim()?.toLowerCase() || '';
    if (text === 'client' || text === 'client:' || text === 'taxpayer' || text === 'taxpayer:' || text === 'name' || text === 'name:') {
      // Check next sibling, parent's next child, or adjacent element
      const next = label.nextElementSibling;
      if (next?.textContent?.trim()) return next.textContent.trim().slice(0, 100);
      const parent = label.parentElement;
      const val = parent?.querySelector('td, dd, .value, span:not(.label)');
      if (val?.textContent?.trim()) return val.textContent.trim().slice(0, 100);
    }
  }

  // Fallback: page title sometimes has client name
  const titleMatch = document.title.match(/(?:Client|Return|Taxpayer)[:\s-]+(.+?)(?:\s*[-|]|$)/i);
  if (titleMatch) return titleMatch[1].trim();

  return '';
}

/**
 * Find IRS form identifiers in the content.
 */
function findFormType(text) {
  const formPatterns = [
    /\bForm\s+(1040[A-Z-]*)\b/i,
    /\bForm\s+(1120[A-Z-]*)\b/i,
    /\bForm\s+(1065[A-Z-]*)\b/i,
    /\bForm\s+(1041[A-Z-]*)\b/i,
    /\bForm\s+(990[A-Z-]*)\b/i,
    /\bForm\s+(706[A-Z-]*)\b/i,
    /\bForm\s+(709[A-Z-]*)\b/i,
    /\b(1040[A-Z-]*)\b/,
    /\b(1120[A-Z-]*)\b/,
    /\b(1065)\b/,
  ];

  for (const pat of formPatterns) {
    const match = text.match(pat);
    if (match) return match[1].toUpperCase();
  }

  return '';
}

/**
 * Find the tax year from the content.
 */
function findTaxYear(text) {
  const currentYear = new Date().getFullYear();

  // Look for "Tax Year YYYY" or "TY YYYY" or "YYYY Tax Return"
  const patterns = [
    /\bTax\s+Year\s+(\d{4})\b/i,
    /\bTY\s+(\d{4})\b/i,
    /\b(\d{4})\s+Tax\s+Return\b/i,
    /\b(\d{4})\s+(?:Federal|State)\s+Return\b/i,
    /\bReturn\s+Year[:\s]+(\d{4})\b/i,
  ];

  for (const pat of patterns) {
    const match = text.match(pat);
    if (match) {
      const year = parseInt(match[1], 10);
      if (year >= 2015 && year <= currentYear + 1) return String(year);
    }
  }

  return '';
}

/**
 * Check if the content contains sensitive data patterns.
 */
function hasSensitiveData(text) {
  // SSN pattern: XXX-XX-XXXX or XXXXXXXXX
  if (/\b\d{3}-\d{2}-\d{4}\b/.test(text)) return true;
  if (/\b\d{9}\b/.test(text) && /\bSSN\b/i.test(text)) return true;
  // EIN pattern: XX-XXXXXXX
  if (/\b\d{2}-\d{7}\b/.test(text)) return true;
  return false;
}

/**
 * Critical security function: mask PII in captured content.
 *
 * Replaces sensitive identifiers with partially masked versions,
 * keeping only the last 4 digits for identification purposes.
 */
export function sanitizeContent(text) {
  let masked = false;

  // Mask SSN: XXX-XX-XXXX → ***-**-XXXX
  let result = text.replace(/\b(\d{3})-(\d{2})-(\d{4})\b/g, (match, p1, p2, p3) => {
    masked = true;
    return `***-**-${p3}`;
  });

  // Mask EIN: XX-XXXXXXX → **-***XXXX (keep last 4)
  result = result.replace(/\b(\d{2})-(\d{7})\b/g, (match, p1, p2) => {
    masked = true;
    return `**-***${p2.slice(-4)}`;
  });

  // Mask bank account numbers: 8+ digit sequences
  // Only match sequences that look like account numbers (not phone numbers, zip codes, dates)
  result = result.replace(/\b(\d{8,17})\b/g, (match) => {
    // Skip if it looks like a phone number (10 digits starting with area code patterns)
    if (/^[2-9]\d{9}$/.test(match)) return match;
    // Skip if it looks like a date (YYYYMMDD)
    if (/^20\d{6}$/.test(match)) return match;
    // Skip common non-sensitive patterns
    if (match.length === 9 && /^[0-9]{5}[0-9]{4}$/.test(match)) return match; // ZIP+4

    masked = true;
    return `***${match.slice(-4)}`;
  });

  // Mask routing numbers: 9-digit sequences near "routing" text
  // This catches cases the general 8+ digit rule might miss due to exactl 9 digits
  result = result.replace(
    /(?:routing|aba|transit)\s*(?:#|number|no\.?)?\s*:?\s*(\d{9})\b/gi,
    (match, digits) => {
      masked = true;
      return match.replace(digits, `***${digits.slice(-4)}`);
    }
  );

  if (masked) {
    console.warn('[Callwen] Sensitive data detected and masked in tax software capture.');
  }

  return result;
}

/**
 * Get the main content area, stripping navigation and UI chrome.
 */
function getMainContent() {
  // Try to find the main content area
  const main = document.querySelector('[role="main"], main, .main-content, #main-content, .content-area');
  if (main) {
    return cleanText(main.innerText || '');
  }

  // Fallback: get body text but strip nav/footer/sidebar
  const body = document.body;
  if (!body) return '';

  const clone = body.cloneNode(true);

  // Remove noise elements
  const noiseSelectors = [
    'nav', 'footer', 'header', '[role="navigation"]', '[role="banner"]',
    '[class*="sidebar"]', '[class*="Sidebar"]', '[class*="nav-"]', '[class*="Nav"]',
    '[class*="footer"]', '[class*="Footer"]', '[class*="menu"]', '[class*="Menu"]',
    '[class*="toolbar"]', '[class*="Toolbar"]', '[class*="cookie"]',
  ];
  noiseSelectors.forEach(sel => {
    clone.querySelectorAll(sel).forEach(el => el.remove());
  });

  return cleanText(clone.innerText || '');
}

/**
 * Clean up extracted text: collapse whitespace, remove excessive blank lines.
 */
function cleanText(text) {
  return text
    .replace(/\t/g, '  ')
    .replace(/ {3,}/g, '  ')
    .replace(/\n{4,}/g, '\n\n\n')
    .trim()
    .slice(0, 500000);
}

/**
 * Format extracted tax data into a clean text document.
 */
export function formatAsDocument(softwareName, data) {
  const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  const sanitized = sanitizeContent(data.raw_content);

  const lines = [];
  lines.push(`Tax Software Export — ${softwareName}`);
  if (data.client_name) lines.push(`Client: ${data.client_name}`);
  if (data.form_type) lines.push(`Form: ${data.form_type}`);
  if (data.tax_year) lines.push(`Tax Year: ${data.tax_year}`);
  lines.push(`Captured: ${timestamp}`);

  if (data.has_sensitive_data) {
    lines.push('[Note: Sensitive identifiers have been partially masked for security.]');
  }

  lines.push('');
  lines.push(sanitized);

  return lines.join('\n');
}

/**
 * Return match hints for auto-matching to a Callwen client.
 */
export function getMatchHints(data) {
  const company_names = [];
  if (data.client_name) company_names.push(data.client_name);
  return { company_names };
}
