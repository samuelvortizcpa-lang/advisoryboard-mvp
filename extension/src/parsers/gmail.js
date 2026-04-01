/**
 * Gmail-specific page parser.
 *
 * Detects Gmail email views and extracts structured data:
 * sender, recipients, subject, date, body text, attachments, thread length.
 * Formats output to match the backend email ingestion format used by
 * gmail_sync_service.py and email_extractor.py.
 */

/**
 * Check if the current page is Gmail.
 */
export function isGmailPage() {
  return window.location.hostname === 'mail.google.com';
}

/**
 * Check if the user is viewing a single email thread (not inbox list).
 * Gmail uses role="main" with a nested email view container.
 */
export function isEmailView() {
  // The email view has an h2 subject header with a data-thread-perm-id
  const subjectEl = document.querySelector('h2[data-thread-perm-id]');
  if (subjectEl) return true;

  // Fallback: check for the email message body container
  const messageBody = document.querySelector('.a3s.aiL');
  if (messageBody) return true;

  return false;
}

/**
 * Extract structured email data from the currently open email thread.
 */
export function extractEmailData() {
  const data = {
    subject: '',
    from_name: '',
    from_email: '',
    to_emails: [],
    cc_emails: [],
    date: '',
    body_text: '',
    attachments: [],
    thread_length: 1,
  };

  // Subject — h2 with thread perm id, or fallback to page title
  const subjectEl = document.querySelector('h2[data-thread-perm-id]');
  if (subjectEl) {
    data.subject = subjectEl.textContent.trim();
  } else {
    // Gmail title format: "Subject - email@gmail.com - Gmail"
    const titleMatch = document.title.match(/^(.+?)\s*-\s*[^-]+@/);
    if (titleMatch) data.subject = titleMatch[1].trim();
  }

  // Sender — .gD elements have name attribute and email in data-hovercard-id or email attr
  const senderEl = document.querySelector('.gD');
  if (senderEl) {
    data.from_name = senderEl.getAttribute('name') || senderEl.textContent?.trim() || '';
    data.from_email = senderEl.getAttribute('email') || '';
  }

  // If no email from .gD, try the hovercard-id pattern
  if (!data.from_email) {
    const hovercardEl = document.querySelector('[data-hovercard-id]');
    if (hovercardEl) {
      const hcId = hovercardEl.getAttribute('data-hovercard-id') || '';
      if (hcId.includes('@')) data.from_email = hcId;
      if (!data.from_name) {
        data.from_name = hovercardEl.textContent?.trim() || '';
      }
    }
  }

  // Recipients — look in the "to" header row
  // Gmail renders recipients in span.g2 elements or similar containers
  const headerRows = document.querySelectorAll('.ajA, .anV');
  headerRows.forEach(row => {
    const spans = row.querySelectorAll('span[email]');
    spans.forEach(span => {
      const email = span.getAttribute('email');
      if (email) data.to_emails.push(email);
    });
  });

  // If no recipients found via ajA/anV, try broader search in header area
  if (data.to_emails.length === 0) {
    const toContainer = document.querySelector('.hb');
    if (toContainer) {
      const emailSpans = toContainer.querySelectorAll('span[email]');
      emailSpans.forEach(span => {
        const email = span.getAttribute('email');
        if (email && email !== data.from_email) {
          data.to_emails.push(email);
        }
      });
    }
  }

  // CC recipients — Gmail shows these in a separate expandable row
  const ccRow = document.querySelector('.ajB');
  if (ccRow) {
    const ccSpans = ccRow.querySelectorAll('span[email]');
    ccSpans.forEach(span => {
      const email = span.getAttribute('email');
      if (email) data.cc_emails.push(email);
    });
  }

  // Date — the date/time element in the email header
  const dateEl = document.querySelector('.g3');
  if (dateEl) {
    // The title attribute has the full date, the text content is relative
    data.date = dateEl.getAttribute('title') || dateEl.textContent?.trim() || '';
  }
  if (!data.date) {
    // Fallback: look for span with date title pattern
    const dateSpans = document.querySelectorAll('span[title]');
    for (const span of dateSpans) {
      const title = span.getAttribute('title') || '';
      // Match patterns like "Mon, Jan 1, 2024, 10:00 AM"
      if (/\d{4}/.test(title) && /\d{1,2}:\d{2}/.test(title)) {
        data.date = title;
        break;
      }
    }
  }

  // Body text — .a3s divs contain the email message body
  // Grab all message bodies in the thread (expanded messages)
  const bodyEls = document.querySelectorAll('.a3s.aiL, .a3s');
  const bodyParts = [];
  const seen = new Set();
  bodyEls.forEach(el => {
    const text = el.innerText?.trim();
    if (text && !seen.has(text)) {
      seen.add(text);
      bodyParts.push(text);
    }
  });
  data.body_text = bodyParts.join('\n\n---\n\n').slice(0, 50000);

  // Attachments — Gmail shows attachment chips with filenames
  const attachmentEls = document.querySelectorAll('.aZo .aV3, .aQy .aV3, [download_url] .aV3');
  attachmentEls.forEach(el => {
    const name = el.textContent?.trim();
    if (name) data.attachments.push(name);
  });

  // Also try the newer attachment chip pattern
  if (data.attachments.length === 0) {
    const chips = document.querySelectorAll('.aZo, .aQH span[data-tooltip]');
    chips.forEach(el => {
      const name = el.getAttribute('data-tooltip') || el.querySelector('.aV3')?.textContent?.trim();
      if (name && name.includes('.')) data.attachments.push(name);
    });
  }

  // Thread length — count message containers
  // Each message in a thread has a .kv or .gs container
  const messages = document.querySelectorAll('.kv, .gs');
  if (messages.length > 0) {
    data.thread_length = messages.length;
  } else {
    // Fallback: count .a3s body divs
    data.thread_length = Math.max(1, bodyEls.length);
  }

  // Deduplicate
  data.to_emails = [...new Set(data.to_emails)];
  data.cc_emails = [...new Set(data.cc_emails)];
  data.attachments = [...new Set(data.attachments)];

  return data;
}

/**
 * Format extracted email data into the text document format that matches
 * the backend's email ingestion (gmail_sync_service.py / email_extractor.py):
 *
 *   From: sender@example.com
 *   To: recipient@example.com
 *   Cc: cc@example.com
 *   Subject: Subject line here
 *   Date: Mon, 01 Jan 2024 10:00:00 +0000
 *
 *   Body:
 *   Email body text...
 */
export function formatAsDocument(emailData) {
  const lines = [];

  if (emailData.from_email) {
    const from = emailData.from_name
      ? `${emailData.from_name} <${emailData.from_email}>`
      : emailData.from_email;
    lines.push(`From: ${from}`);
  }

  if (emailData.to_emails.length > 0) {
    lines.push(`To: ${emailData.to_emails.join(', ')}`);
  }

  if (emailData.cc_emails.length > 0) {
    lines.push(`Cc: ${emailData.cc_emails.join(', ')}`);
  }

  if (emailData.subject) {
    lines.push(`Subject: ${emailData.subject}`);
  }

  if (emailData.date) {
    lines.push(`Date: ${emailData.date}`);
  }

  if (emailData.attachments.length > 0) {
    lines.push(`Attachments: ${emailData.attachments.join(', ')}`);
  }

  if (emailData.thread_length > 1) {
    lines.push(`Thread: ${emailData.thread_length} messages`);
  }

  // Blank line separator between headers and body
  lines.push('');
  lines.push('Body:');
  lines.push(emailData.body_text || '');

  return lines.join('\n');
}

/**
 * Return data useful for auto-matching this email to a client.
 * Collects all email addresses and extracts company-like names from domains.
 */
export function getMatchHints(emailData) {
  // Collect all email addresses
  const allEmails = [];
  if (emailData.from_email) allEmails.push(emailData.from_email);
  allEmails.push(...(emailData.to_emails || []));
  allEmails.push(...(emailData.cc_emails || []));
  const email_addresses = [...new Set(allEmails)];

  // Extract company names from email domains
  // e.g., "john@smithfamily.com" → "smithfamily"
  // Skip common free email providers
  const freeProviders = new Set([
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com',
    'icloud.com', 'mail.com', 'protonmail.com', 'zoho.com', 'yandex.com',
    'live.com', 'msn.com', 'comcast.net', 'att.net', 'verizon.net',
  ]);

  const company_names = [];
  for (const email of email_addresses) {
    const domain = email.split('@')[1]?.toLowerCase();
    if (!domain || freeProviders.has(domain)) continue;
    // Take the part before the TLD: "acme.co.uk" → "acme"
    const parts = domain.split('.');
    const name = parts[0];
    if (name && name.length > 1) {
      company_names.push(name);
    }
  }

  // Also use the sender's display name if it looks like a company
  if (emailData.from_name && !emailData.from_name.includes('@')) {
    company_names.push(emailData.from_name);
  }

  return {
    email_addresses,
    company_names: [...new Set(company_names)],
  };
}
