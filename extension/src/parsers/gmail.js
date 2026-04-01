/**
 * Gmail-specific page parser.
 *
 * Detects Gmail email views and extracts structured data:
 * sender, recipients, subject, date, body text.
 */

export function isGmailPage() {
  return window.location.hostname === 'mail.google.com';
}

export function parseGmailEmail() {
  // Gmail renders emails in deeply nested divs. The most reliable
  // selectors target the email header and body areas.
  const subject = document.querySelector('h2[data-thread-perm-id]')?.textContent || '';
  const senderEl = document.querySelector('[data-hovercard-id]');
  const sender = senderEl?.getAttribute('data-hovercard-id') || senderEl?.textContent || '';

  // Email body — usually the last .a3s div
  const bodyEls = document.querySelectorAll('.a3s');
  const body = bodyEls.length ? bodyEls[bodyEls.length - 1].innerText : '';

  return {
    type: 'gmail_email',
    subject,
    sender,
    body: body.slice(0, 50000),
    url: window.location.href,
  };
}
