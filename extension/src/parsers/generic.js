/**
 * Generic page parser — fallback for any webpage.
 *
 * Extracts basic metadata: title, URL, visible text.
 */

export function parseGenericPage() {
  const bodyText = document.body?.innerText?.slice(0, 50000) || '';
  const title = document.title || '';
  const description = document.querySelector('meta[name="description"]')?.content || '';

  return {
    type: 'generic',
    page_title: title,
    description,
    content: bodyText,
    url: window.location.href,
    domain: window.location.hostname,
  };
}
