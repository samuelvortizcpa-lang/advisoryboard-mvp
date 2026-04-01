/**
 * QuickBooks Online parser.
 *
 * Detects QBO page types (report, transaction, customer list, dashboard)
 * and extracts structured financial data for cleaner document capture.
 */

export function isQuickBooksPage() {
  return window.location.hostname.includes('qbo.intuit.com') ||
    window.location.hostname.includes('quickbooks.intuit.com');
}

/**
 * Identify what type of QBO page the user is viewing.
 */
export function detectQBOPage() {
  const url = window.location.href.toLowerCase();
  const path = window.location.pathname.toLowerCase();

  // Reports — URL patterns and page elements
  if (
    path.includes('/report') ||
    url.includes('reporttype') ||
    document.querySelector('[data-automation="report-header"]') ||
    document.querySelector('.report-header, .reportHeader') ||
    document.querySelector('[data-testid="report-title"]')
  ) {
    return 'report';
  }

  // Transactions — invoices, bills, journal entries, expenses
  if (
    path.includes('/invoice') ||
    path.includes('/bill') ||
    path.includes('/journalentry') ||
    path.includes('/expense') ||
    path.includes('/check') ||
    path.includes('/deposit') ||
    path.includes('/creditmemo') ||
    path.includes('/estimate') ||
    path.includes('/purchaseorder') ||
    path.includes('/salesreceipt') ||
    path.includes('/vendorcredit') ||
    path.includes('/payment') ||
    path.includes('/transfer') ||
    document.querySelector('[data-automation="transaction-header"]') ||
    document.querySelector('.transaction-header, .txn-header')
  ) {
    return 'transaction';
  }

  // Customer/Vendor lists
  if (
    path.includes('/customers') ||
    path.includes('/vendors') ||
    path.includes('/contacts') ||
    document.querySelector('[data-automation="customer-list"]') ||
    document.querySelector('[data-automation="vendor-list"]')
  ) {
    return 'customer_list';
  }

  // Dashboard
  if (
    path === '/' ||
    path.includes('/dashboard') ||
    path.includes('/homepage') ||
    document.querySelector('[data-automation="dashboard"]')
  ) {
    return 'dashboard';
  }

  return 'unknown';
}

/**
 * Get the company name from the QBO header/nav.
 */
function getCompanyName() {
  const selectors = [
    '[data-automation-id="company-name"]',
    '[data-automation="company-name"]',
    '.company-name',
    '[class*="CompanyName"]',
    '[data-testid="company-name"]',
    // Nav area company display
    '.LeftNav [class*="company"]',
    '#globalNavCompanyName',
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    const text = el?.textContent?.trim();
    if (text && text.length < 100) return text;
  }

  // Fallback: check the page title ("Company Name - QuickBooks")
  const titleMatch = document.title.match(/^(.+?)\s*[-|]\s*QuickBooks/i);
  if (titleMatch) return titleMatch[1].trim();

  return '';
}

/**
 * Extract structured data from a QBO report page.
 */
export function extractReportData() {
  const data = {
    report_title: '',
    date_range: '',
    company_name: getCompanyName(),
    table_data: '',
  };

  // Report title
  const titleEl = document.querySelector(
    '[data-testid="report-title"], [data-automation="report-header"] h1, ' +
    '.report-header h1, .reportHeader h1, .report-title, [class*="ReportTitle"]'
  );
  if (titleEl) {
    data.report_title = titleEl.textContent.trim();
  } else {
    // Fallback: page title often has the report name
    const match = document.title.match(/^(.+?)\s*[-|]/);
    if (match) data.report_title = match[1].trim();
  }

  // Date range — usually near the title
  const dateEl = document.querySelector(
    '[data-testid="report-date-range"], .report-date-range, [class*="DateRange"], ' +
    '[data-automation="report-period"], .report-period'
  );
  if (dateEl) {
    data.date_range = dateEl.textContent.trim();
  } else {
    // Look for date text patterns near the report header
    const headerArea = document.querySelector('.report-header, .reportHeader, [data-automation="report-header"]');
    if (headerArea) {
      const text = headerArea.innerText || '';
      // Match date range patterns like "January - March 2026" or "01/01/2026 to 03/31/2026"
      const dateMatch = text.match(
        /(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+.*?\d{4}/i
      ) || text.match(/\d{1,2}\/\d{1,2}\/\d{4}\s*(?:to|-)\s*\d{1,2}\/\d{1,2}\/\d{4}/);
      if (dateMatch) data.date_range = dateMatch[0].trim();
    }
  }

  // Extract table data
  data.table_data = extractTableText();

  return data;
}

/**
 * Extract structured data from a QBO transaction page.
 */
export function extractTransactionData() {
  const data = {
    transaction_type: '',
    transaction_number: '',
    date: '',
    vendor_or_customer: '',
    amount: '',
    line_items: [],
    company_name: getCompanyName(),
  };

  // Transaction type from page title or header
  const typeEl = document.querySelector(
    '[data-automation="transaction-header"] h1, .transaction-header h1, ' +
    '.txn-header h1, [data-testid="txn-type"]'
  );
  if (typeEl) {
    data.transaction_type = typeEl.textContent.trim();
  } else {
    const path = window.location.pathname.toLowerCase();
    if (path.includes('/invoice')) data.transaction_type = 'Invoice';
    else if (path.includes('/bill')) data.transaction_type = 'Bill';
    else if (path.includes('/journalentry')) data.transaction_type = 'Journal Entry';
    else if (path.includes('/expense')) data.transaction_type = 'Expense';
    else if (path.includes('/check')) data.transaction_type = 'Check';
    else if (path.includes('/deposit')) data.transaction_type = 'Deposit';
    else if (path.includes('/creditmemo')) data.transaction_type = 'Credit Memo';
    else if (path.includes('/estimate')) data.transaction_type = 'Estimate';
    else if (path.includes('/purchaseorder')) data.transaction_type = 'Purchase Order';
    else if (path.includes('/salesreceipt')) data.transaction_type = 'Sales Receipt';
    else if (path.includes('/vendorcredit')) data.transaction_type = 'Vendor Credit';
    else if (path.includes('/payment')) data.transaction_type = 'Payment';
    else if (path.includes('/transfer')) data.transaction_type = 'Transfer';
    else data.transaction_type = 'Transaction';
  }

  // Transaction/reference number
  const numEl = document.querySelector(
    '[data-testid="txn-number"], [data-automation="txn-number"], ' +
    'input[name*="DocNumber"], input[name*="docNumber"], ' +
    '[class*="docNumber"], [class*="referenceNumber"]'
  );
  if (numEl) {
    data.transaction_number = (numEl.value || numEl.textContent || '').trim();
  }

  // Date
  const dateEl = document.querySelector(
    '[data-testid="txn-date"], [data-automation="txn-date"], ' +
    'input[name*="TxnDate"], input[name*="txnDate"], input[name*="date"]'
  );
  if (dateEl) {
    data.date = (dateEl.value || dateEl.textContent || '').trim();
  }

  // Vendor or Customer name
  const entityEl = document.querySelector(
    '[data-testid="customer-name"], [data-testid="vendor-name"], ' +
    '[data-automation="customer-select"], [data-automation="vendor-select"], ' +
    '[class*="CustomerName"], [class*="VendorName"], ' +
    '[data-automation="payee-select"]'
  );
  if (entityEl) {
    // Could be an input or a display element
    data.vendor_or_customer = (entityEl.value || entityEl.textContent || '').trim();
  }

  // Total amount
  const amountEl = document.querySelector(
    '[data-testid="total-amount"], [data-automation="total-amount"], ' +
    '[class*="totalAmount"], [class*="TotalAmount"], ' +
    '[data-testid="balance-due"], [data-automation="balance-due"]'
  );
  if (amountEl) {
    data.amount = amountEl.textContent?.trim() || '';
  }

  // Line items from the transaction table
  const lineRows = document.querySelectorAll(
    '[data-automation="line-item"], [data-testid="line-item"], ' +
    'tr[class*="line-item"], tr[class*="lineItem"]'
  );
  lineRows.forEach(row => {
    const cells = row.querySelectorAll('td, [role="cell"]');
    if (cells.length >= 2) {
      const item = {
        description: '',
        amount: '',
        account: '',
      };
      // QBO line items typically have: description/product, qty, rate, amount, account
      cells.forEach(cell => {
        const text = cell.textContent?.trim() || '';
        const testId = cell.getAttribute('data-testid') || cell.getAttribute('data-automation') || '';
        if (testId.includes('description') || testId.includes('product')) {
          item.description = text;
        } else if (testId.includes('amount') || testId.includes('total')) {
          item.amount = text;
        } else if (testId.includes('account') || testId.includes('category')) {
          item.account = text;
        }
      });
      // Fallback: use positional extraction
      if (!item.description && cells[0]) item.description = cells[0].textContent?.trim() || '';
      if (!item.amount && cells[cells.length - 1]) item.amount = cells[cells.length - 1].textContent?.trim() || '';
      if (item.description || item.amount) {
        data.line_items.push(item);
      }
    }
  });

  // If no line items found via data attributes, try generic table rows
  if (data.line_items.length === 0) {
    const tables = document.querySelectorAll('table');
    for (const table of tables) {
      const rows = table.querySelectorAll('tbody tr');
      if (rows.length > 0 && rows.length < 100) {
        rows.forEach(row => {
          const cells = row.querySelectorAll('td');
          if (cells.length >= 2) {
            const desc = cells[0]?.textContent?.trim() || '';
            const amt = cells[cells.length - 1]?.textContent?.trim() || '';
            if (desc && /[\d$.,]/.test(amt)) {
              data.line_items.push({ description: desc, amount: amt, account: '' });
            }
          }
        });
        if (data.line_items.length > 0) break;
      }
    }
  }

  return data;
}

/**
 * Extract table content from the page as formatted text.
 * Handles QBO report tables with nested rows and indentation.
 */
function extractTableText() {
  const tables = document.querySelectorAll(
    '[data-automation="report-table"] table, .report-table table, ' +
    '[class*="ReportTable"] table, [data-testid="report-table"] table, ' +
    'table[class*="report"]'
  );

  // If no specific report table found, try the largest table on the page
  const targetTables = tables.length > 0
    ? tables
    : getLargestTables();

  if (targetTables.length === 0) {
    // Last resort: grab visible text from the main content area
    const main = document.querySelector('[role="main"], main, .main-content');
    return main ? main.innerText.slice(0, 30000) : '';
  }

  const lines = [];

  for (const table of targetTables) {
    // Headers
    const headerRow = table.querySelector('thead tr');
    if (headerRow) {
      const headers = [];
      headerRow.querySelectorAll('th, td').forEach(cell => {
        headers.push(cell.textContent?.trim() || '');
      });
      if (headers.some(h => h)) {
        lines.push(headers.join('\t'));
        lines.push(headers.map(h => '-'.repeat(Math.max(h.length, 3))).join('\t'));
      }
    }

    // Body rows
    const bodyRows = table.querySelectorAll('tbody tr, tr');
    bodyRows.forEach(row => {
      // Skip header rows we already processed
      if (row.closest('thead')) return;

      const cells = [];
      row.querySelectorAll('td, th').forEach(cell => {
        cells.push(cell.textContent?.trim() || '');
      });
      if (cells.some(c => c)) {
        lines.push(cells.join('\t'));
      }
    });

    lines.push(''); // blank line between tables
  }

  return lines.join('\n').slice(0, 50000);
}

/**
 * Find the largest tables on the page (likely the report data).
 */
function getLargestTables() {
  const allTables = [...document.querySelectorAll('table')];
  // Sort by row count, take the top one with meaningful data
  return allTables
    .filter(t => t.querySelectorAll('tr').length >= 3)
    .sort((a, b) => b.querySelectorAll('tr').length - a.querySelectorAll('tr').length)
    .slice(0, 2);
}

/**
 * Return data useful for auto-matching this QBO page to a client.
 */
export function getMatchHints() {
  const company_names = [];
  const name = getCompanyName();
  if (name) company_names.push(name);
  return { company_names };
}

/**
 * Format extracted QBO data into a clean text document.
 */
export function formatAsDocument(pageType, data) {
  const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  const lines = [];

  if (pageType === 'report') {
    lines.push(`QuickBooks Online — ${data.report_title || 'Report'}`);
    if (data.company_name) lines.push(`Company: ${data.company_name}`);
    if (data.date_range) lines.push(`Period: ${data.date_range}`);
    lines.push(`Captured: ${timestamp}`);
    lines.push('');
    if (data.table_data) {
      lines.push(data.table_data);
    }
  } else if (pageType === 'transaction') {
    lines.push(`QuickBooks Online — ${data.transaction_type || 'Transaction'}`);
    if (data.company_name) lines.push(`Company: ${data.company_name}`);
    if (data.transaction_number) lines.push(`Number: ${data.transaction_number}`);
    if (data.date) lines.push(`Date: ${data.date}`);
    if (data.vendor_or_customer) lines.push(`Entity: ${data.vendor_or_customer}`);
    if (data.amount) lines.push(`Amount: ${data.amount}`);
    lines.push(`Captured: ${timestamp}`);
    lines.push('');

    if (data.line_items.length > 0) {
      lines.push('Line Items:');
      lines.push('Description\tAccount\tAmount');
      lines.push('-----------\t-------\t------');
      data.line_items.forEach(item => {
        const desc = item.description || '';
        const acct = item.account || '';
        const amt = item.amount || '';
        lines.push(`${desc}\t${acct}\t${amt}`);
      });
    }
  }

  return lines.join('\n');
}
