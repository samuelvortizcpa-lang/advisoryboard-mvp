/**
 * Capture logic — text selection, full page, file URL, screenshot.
 */

import { CONFIG } from '../utils/config.js';
import { captureContent } from './api.js';

/**
 * Capture the current text selection from the active tab.
 */
export async function captureTextSelection(tab, clientId, documentTag) {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.getSelection().toString(),
  });

  const text = result?.result;
  if (!text || !text.trim()) {
    throw new Error('No text selected on the page.');
  }

  if (text.length > CONFIG.MAX_TEXT_LENGTH) {
    throw new Error(`Selection too large (${text.length} chars). Max ${CONFIG.MAX_TEXT_LENGTH}.`);
  }

  return captureContent({
    client_id: clientId,
    capture_type: 'text_selection',
    content: text,
    metadata: _pageMetadata(tab),
    document_tag: documentTag,
  });
}

/**
 * Capture the full page text content.
 */
export async function captureFullPage(tab, clientId, documentTag) {
  const [result] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => document.body.innerText,
  });

  const text = result?.result;
  if (!text || !text.trim()) {
    throw new Error('Page has no text content.');
  }

  const content = text.length > CONFIG.MAX_TEXT_LENGTH
    ? text.slice(0, CONFIG.MAX_TEXT_LENGTH)
    : text;

  return captureContent({
    client_id: clientId,
    capture_type: 'full_page',
    content,
    metadata: _pageMetadata(tab),
    document_tag: documentTag,
  });
}

/**
 * Capture a file by its URL (the backend fetches it server-side).
 */
export async function captureFileUrl(tab, clientId, fileUrl, documentTag) {
  return captureContent({
    client_id: clientId,
    capture_type: 'file_url',
    file_url: fileUrl,
    metadata: _pageMetadata(tab),
    document_tag: documentTag,
  });
}

/**
 * Capture a screenshot of the visible tab.
 */
export async function captureScreenshot(tab, clientId, documentTag) {
  const dataUrl = await chrome.tabs.captureVisibleTab(null, {
    format: 'png',
    quality: 90,
  });

  // Strip the data:image/png;base64, prefix
  const base64 = dataUrl.split(',')[1];

  return captureContent({
    client_id: clientId,
    capture_type: 'screenshot',
    image_data: base64,
    metadata: _pageMetadata(tab),
    document_tag: documentTag,
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _pageMetadata(tab) {
  const url = tab.url || '';
  let domain = '';
  try {
    domain = new URL(url).hostname;
  } catch {
    // invalid URL
  }

  return {
    url,
    page_title: tab.title || '',
    captured_at: new Date().toISOString(),
    site_domain: domain,
  };
}
