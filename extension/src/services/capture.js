/**
 * Capture orchestration.
 *
 * Each function talks to the content script to extract data from the active
 * tab, then returns a structured payload ready for the API. The popup calls
 * these, then passes the result to api.captureContent().
 */

import { CONFIG } from '../utils/config.js';

// ---------------------------------------------------------------------------
// Text selection
// ---------------------------------------------------------------------------

export async function captureTextSelection(tabId) {
  const response = await sendToContentScript(tabId, { type: 'GET_SELECTED_TEXT' });
  const text = response?.text?.trim();

  if (!text) {
    throw new Error('No text selected on this page.');
  }
  if (text.length > CONFIG.MAX_TEXT_LENGTH) {
    throw new Error(`Selection too large (${text.length.toLocaleString()} chars). Max ${CONFIG.MAX_TEXT_LENGTH.toLocaleString()}.`);
  }

  return {
    type: 'text_selection',
    content: text,
  };
}

// ---------------------------------------------------------------------------
// Full page
// ---------------------------------------------------------------------------

export async function captureFullPage(tabId) {
  const response = await sendToContentScript(tabId, { type: 'GET_PAGE_TEXT' });
  const text = response?.text?.trim();

  if (!text) {
    throw new Error('No content found on this page.');
  }

  return {
    type: 'full_page',
    content: text.slice(0, CONFIG.MAX_TEXT_LENGTH),
  };
}

// ---------------------------------------------------------------------------
// File URL
// ---------------------------------------------------------------------------

export async function captureFileUrl(url) {
  if (!url) {
    throw new Error('No file URL provided.');
  }

  try {
    new URL(url);
  } catch {
    throw new Error('Invalid URL format.');
  }

  // Extract filename from URL path
  let filename = '';
  try {
    const pathname = new URL(url).pathname;
    const segments = pathname.split('/').filter(Boolean);
    if (segments.length > 0) {
      filename = decodeURIComponent(segments[segments.length - 1]);
    }
  } catch { /* best-effort */ }

  return {
    type: 'file_url',
    file_url: url,
    filename,
  };
}

// ---------------------------------------------------------------------------
// Screenshot (region selection via content script, capture via background)
// ---------------------------------------------------------------------------

export async function captureScreenshot(tabId) {
  // Ask content script to let user select a region
  const response = await sendToContentScript(tabId, { type: 'START_SCREENSHOT_SELECTION' });

  if (!response?.region) {
    throw new Error('Screenshot cancelled.');
  }

  const region = response.region;

  // Capture the full visible tab (only the service worker / background can do this)
  const dataUrl = await chrome.tabs.captureVisibleTab(null, {
    format: 'png',
    quality: 100,
  });

  // Crop to the selected region using an offscreen canvas
  const croppedBase64 = await cropImage(dataUrl, region);

  return {
    type: 'screenshot',
    image_data: croppedBase64,
  };
}

// ---------------------------------------------------------------------------
// Page metadata
// ---------------------------------------------------------------------------

export async function getPageMetadata(tabId) {
  const response = await sendToContentScript(tabId, { type: 'GET_PAGE_METADATA' });

  if (!response) {
    throw new Error('Could not get page metadata. The content script may not be loaded.');
  }

  return {
    url: response.url || '',
    title: response.title || '',
    domain: response.domain || '',
    site_type: response.site_type || 'generic',
    emails: response.email_addresses || [],
    companyNames: response.company_names || [],
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Send a message to the content script in the given tab.
 * Wraps chrome.tabs.sendMessage with a timeout.
 */
async function sendToContentScript(tabId, message) {
  try {
    return await trySendMessage(tabId, message);
  } catch {
    // Content script may not be injected yet — try injecting it manually
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: ['content-script.js'],
      });
      return await trySendMessage(tabId, message);
    } catch (retryErr) {
      throw new Error(
        'Cannot access this page. Try refreshing the page or switching to a regular web page.'
      );
    }
  }
}

function trySendMessage(tabId, message) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Content script did not respond.'));
    }, 10000);

    chrome.tabs.sendMessage(tabId, message, (response) => {
      clearTimeout(timeout);
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

/**
 * Crop an image data URL to the given region.
 * Uses an OffscreenCanvas (available in service workers) or falls back
 * to a regular canvas (for popup context).
 */
async function cropImage(dataUrl, region) {
  // Load the image
  const blob = await (await fetch(dataUrl)).blob();
  const bitmap = await createImageBitmap(blob);

  // Clamp region to image bounds
  const x = Math.max(0, Math.round(region.x));
  const y = Math.max(0, Math.round(region.y));
  const w = Math.min(Math.round(region.width), bitmap.width - x);
  const h = Math.min(Math.round(region.height), bitmap.height - y);

  if (w <= 0 || h <= 0) {
    throw new Error('Invalid screenshot region.');
  }

  // Use OffscreenCanvas (works in service workers and modern browsers)
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d');
  ctx.drawImage(bitmap, x, y, w, h, 0, 0, w, h);
  bitmap.close();

  const outputBlob = await canvas.convertToBlob({ type: 'image/png' });

  // Convert blob to base64
  const buffer = await outputBlob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
