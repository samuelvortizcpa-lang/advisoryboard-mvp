/**
 * Side panel — Quick Query AI interface.
 *
 * Lets users ask questions against a client's document corpus via the
 * existing RAG endpoint. Session-only chat (not persisted). Single-turn
 * questions only (no multi-turn context). Paid tiers only.
 */

import { isAuthenticated, signIn } from '../services/auth.js';
import {
  getExtensionConfig, getClients, askQuestion, ERROR_CODES,
} from '../services/api.js';
import { getRecentClientIds } from '../utils/storage.js';

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const authScreen = document.getElementById('auth-screen');
const tierGate = document.getElementById('tier-gate');
const mainScreen = document.getElementById('main-screen');
const signInBtn = document.getElementById('sign-in-btn');

const spClientBtn = document.getElementById('sp-client-btn');
const spClientText = document.getElementById('sp-client-text');
const spClientDropdown = document.getElementById('sp-client-dropdown');
const spClientSearch = document.getElementById('sp-client-search');
const spClientList = document.getElementById('sp-client-list');

const chatMessages = document.getElementById('chat-messages');
const contextBanner = document.getElementById('context-banner');
const insertContextBtn = document.getElementById('insert-context-btn');
const dismissContextBtn = document.getElementById('dismiss-context-btn');
const queryInput = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const throttleMsg = document.getElementById('throttle-msg');

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let allClients = [];
let recentClientIds = [];
let selectedClientId = '';
let selectedClientName = '';
let selectedText = '';       // text selected on the active page
let chatHistory = [];        // { role: 'user'|'ai', content, confidence?, sources? }
const queryTimestamps = [];  // for client-side throttle

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  const authed = await isAuthenticated();
  if (!authed) {
    showScreen('auth');
    return;
  }

  try {
    const config = await getExtensionConfig();
    if (!config.quick_query) {
      showScreen('tier');
      return;
    }
  } catch (err) {
    if (err.code === ERROR_CODES.AUTH_EXPIRED) {
      showScreen('auth');
      return;
    }
    // Can't verify tier — let them try
  }

  showScreen('main');

  // Load clients
  try {
    const clients = await getClients();
    allClients = Array.isArray(clients) ? clients : [];
    recentClientIds = await getRecentClientIds();
    renderClientList();
  } catch { /* client list fails — dropdown stays empty */ }

  // Check for pre-selected client from popup/auto-match
  try {
    const session = await chrome.storage.session.get(['sidepanel_client', 'selected_client_id', 'selected_client_name']);
    if (session.sidepanel_client) {
      const { id, name } = session.sidepanel_client;
      if (id && allClients.some(c => c.id === id)) {
        selectClient(id, name);
      }
      await chrome.storage.session.remove('sidepanel_client');
    } else if (session.selected_client_id) {
      const id = session.selected_client_id;
      const name = session.selected_client_name || allClients.find(c => c.id === id)?.name || 'Unknown';
      if (allClients.some(c => c.id === id)) {
        selectClient(id, name);
      }
    }
  } catch { /* no pre-selection */ }

  // Check for selected text on the active page
  await checkSelectedText();

  // Check for pre-filled query text from context menu
  try {
    const session = await chrome.storage.session.get('sidepanel_query');
    if (session.sidepanel_query) {
      queryInput.value = session.sidepanel_query;
      autoResizeInput();
      await chrome.storage.session.remove('sidepanel_query');
    }
  } catch { /* no pre-fill */ }
}

function showScreen(name) {
  authScreen.classList.toggle('hidden', name !== 'auth');
  tierGate.classList.toggle('hidden', name !== 'tier');
  mainScreen.classList.toggle('hidden', name !== 'main');
}

// ---------------------------------------------------------------------------
// Client picker
// ---------------------------------------------------------------------------

function renderClientList(filter = '') {
  const query = filter.toLowerCase().trim();
  const sorted = [...allClients].sort((a, b) =>
    (a.name || '').localeCompare(b.name || ''));

  const recentSet = new Set(recentClientIds);
  const recentClients = recentClientIds
    .map(id => sorted.find(c => c.id === id))
    .filter(Boolean);
  const otherClients = sorted.filter(c => !recentSet.has(c.id));

  const matchFn = (c) => {
    if (!query) return true;
    return (c.name || '').toLowerCase().includes(query) ||
           (c.business_name || '').toLowerCase().includes(query);
  };

  let html = '';

  // Recently used
  const filteredRecent = recentClients.filter(matchFn);
  if (filteredRecent.length > 0 && !query) {
    html += '<div class="sp-client-divider">Recently used</div>';
    filteredRecent.slice(0, 3).forEach(c => {
      html += clientOptionHtml(c);
    });
  }

  // All (or filtered)
  const list = query ? sorted.filter(matchFn) : otherClients;
  if (list.length > 0) {
    if (!query) html += '<div class="sp-client-divider">All clients</div>';
    list.forEach(c => {
      if (!query && recentSet.has(c.id)) return;
      html += clientOptionHtml(c);
    });
  }

  if (!html) {
    html = '<div class="sp-client-empty">No clients found</div>';
  }

  spClientList.innerHTML = html;

  spClientList.querySelectorAll('.sp-client-option').forEach(el => {
    el.addEventListener('click', () => {
      selectClient(el.dataset.id, el.dataset.name);
      closeDropdown();
    });
  });
}

function clientOptionHtml(c) {
  const sel = c.id === selectedClientId ? ' selected' : '';
  const label = c.business_name ? `${c.name} — ${c.business_name}` : c.name;
  return `<div class="sp-client-option${sel}" data-id="${c.id}" data-name="${esc(c.name || 'Unnamed')}">${esc(label)}</div>`;
}

function selectClient(id, name) {
  // If switching clients, clear chat
  if (selectedClientId && selectedClientId !== id) {
    clearChat();
  }

  selectedClientId = id;
  selectedClientName = name;
  spClientText.textContent = name;
  spClientText.classList.remove('placeholder');
  queryInput.disabled = false;
  queryInput.placeholder = `Ask about ${name}'s documents...`;
  updateSendBtn();

  // Highlight in list
  spClientList.querySelectorAll('.sp-client-option').forEach(el => {
    el.classList.toggle('selected', el.dataset.id === id);
  });

  // Sync to session storage so popup can pick it up
  chrome.storage.session.set({
    selected_client_id: id,
    selected_client_name: name,
  }).catch(() => {});
}

spClientBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  if (spClientDropdown.classList.contains('hidden')) openDropdown();
  else closeDropdown();
});

function openDropdown() {
  spClientDropdown.classList.remove('hidden');
  spClientBtn.classList.add('open');
  spClientSearch.value = '';
  renderClientList();
  setTimeout(() => spClientSearch.focus(), 10);
}

function closeDropdown() {
  spClientDropdown.classList.add('hidden');
  spClientBtn.classList.remove('open');
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('#sp-client-picker')) closeDropdown();
});

spClientSearch.addEventListener('input', () => {
  renderClientList(spClientSearch.value);
});

spClientSearch.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { closeDropdown(); return; }
  if (e.key === 'Enter') {
    const first = spClientList.querySelector('.sp-client-option');
    if (first) {
      selectClient(first.dataset.id, first.dataset.name);
      closeDropdown();
    }
  }
});

// ---------------------------------------------------------------------------
// Selected text context
// ---------------------------------------------------------------------------

async function checkSelectedText() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;
    const response = await chrome.tabs.sendMessage(tab.id, { type: 'GET_SELECTED_TEXT' });
    const text = response?.text?.trim();
    if (text && text.length > 0) {
      selectedText = text;
      contextBanner.classList.remove('hidden');
    }
  } catch { /* no access */ }
}

insertContextBtn.addEventListener('click', () => {
  if (!selectedText) return;
  const quote = selectedText.length > 500
    ? selectedText.slice(0, 500) + '...'
    : selectedText;
  queryInput.value = `> ${quote.replace(/\n/g, '\n> ')}\n\n`;
  autoResizeInput();
  queryInput.focus();
  contextBanner.classList.add('hidden');
});

dismissContextBtn.addEventListener('click', () => {
  contextBanner.classList.add('hidden');
  selectedText = '';
});

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

function clearChat() {
  chatHistory = [];
  chatMessages.innerHTML = `
    <div class="chat-empty">
      <p class="chat-empty-title">Ask anything</p>
      <p class="chat-empty-desc">Questions are answered using your client's uploaded documents with source citations.</p>
    </div>`;
}

function addUserMessage(text) {
  // Remove empty state if present
  const empty = chatMessages.querySelector('.chat-empty');
  if (empty) empty.remove();

  chatHistory.push({ role: 'user', content: text });

  const el = document.createElement('div');
  el.className = 'msg-user';
  el.textContent = text;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function addTypingIndicator() {
  const el = document.createElement('div');
  el.className = 'msg-typing';
  el.id = 'typing-indicator';
  el.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  chatMessages.appendChild(el);
  scrollToBottom();
}

function removeTypingIndicator() {
  const el = document.getElementById('typing-indicator');
  if (el) el.remove();
}

function addAiMessage(answer, confidenceTier, confidenceScore, sources) {
  chatHistory.push({
    role: 'ai', content: answer,
    confidence: confidenceTier, score: confidenceScore, sources,
  });

  const el = document.createElement('div');
  el.className = 'msg-ai';

  // Confidence row
  const tier = (confidenceTier || 'medium').toLowerCase();
  const pct = confidenceScore != null ? `${Math.round(confidenceScore * 100)}%` : '';
  const tierLabel = tier.charAt(0).toUpperCase() + tier.slice(1);

  let html = `<div class="confidence-row">
    <span class="confidence-dot ${tier}"></span>
    <span class="confidence-label">${tierLabel} confidence</span>
    ${pct ? `<span class="confidence-pct">${pct}</span>` : ''}
  </div>`;

  // Answer text
  html += `<div class="msg-ai-text">${esc(answer)}</div>`;

  // Sources
  if (sources && sources.length > 0) {
    html += '<div class="sources-row">';
    sources.forEach((src, i) => {
      const name = src.document_name || src.filename || `Source ${i + 1}`;
      const score = src.score != null ? (src.score * 100).toFixed(0) + '%' : '';
      html += `<div class="source-pill" data-idx="${i}">
        <span class="source-pill-name">${esc(name)}</span>
        ${score ? `<span class="source-pill-score">${score}</span>` : ''}
      </div>`;
    });
    html += '</div>';
    // Hidden preview containers
    sources.forEach((src, i) => {
      const preview = src.chunk_text || src.content || '';
      if (preview) {
        html += `<div class="source-preview hidden" data-preview-idx="${i}">${esc(preview.slice(0, 300))}</div>`;
      }
    });
  }

  el.innerHTML = html;

  // Source pill click → toggle preview
  el.querySelectorAll('.source-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      const idx = pill.dataset.idx;
      const preview = el.querySelector(`[data-preview-idx="${idx}"]`);
      if (preview) preview.classList.toggle('hidden');
    });
  });

  chatMessages.appendChild(el);
  scrollToBottom();
}

function addErrorMessage(text) {
  const el = document.createElement('div');
  el.className = 'msg-ai';
  el.innerHTML = `<div class="msg-ai-text" style="color: #ef4444;">${esc(text)}</div>`;
  chatMessages.appendChild(el);
  scrollToBottom();
}

function scrollToBottom() {
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ---------------------------------------------------------------------------
// Send question
// ---------------------------------------------------------------------------

async function handleSend() {
  const question = queryInput.value.trim();
  if (!question || !selectedClientId) return;

  // Client-side throttle: max 3 per minute
  const now = Date.now();
  const recentQueries = queryTimestamps.filter(t => now - t < 60000);
  if (recentQueries.length >= 3) {
    throttleMsg.classList.remove('hidden');
    setTimeout(() => throttleMsg.classList.add('hidden'), 3000);
    return;
  }
  queryTimestamps.push(now);

  // Clear input
  queryInput.value = '';
  autoResizeInput();
  updateSendBtn();

  addUserMessage(question);
  addTypingIndicator();
  setInputEnabled(false);

  try {
    const response = await askQuestion(selectedClientId, question);

    removeTypingIndicator();

    // Parse RAG response — the backend returns various shapes
    const answer = response.response || response.answer || response.message || 'No answer available.';
    const confidenceTier = response.confidence_tier || response.confidence || 'medium';
    const confidenceScore = response.confidence_score ?? response.score ?? null;
    const sources = response.sources || response.citations || [];

    addAiMessage(answer, confidenceTier, confidenceScore, sources);
  } catch (err) {
    removeTypingIndicator();

    if (err.code === ERROR_CODES.AUTH_EXPIRED) {
      addErrorMessage('Session expired. Please sign in again.');
      showScreen('auth');
      return;
    }
    addErrorMessage(err.message || 'Something went wrong. Please try again.');
  }

  setInputEnabled(true);
  queryInput.focus();
}

function setInputEnabled(enabled) {
  queryInput.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

function updateSendBtn() {
  sendBtn.disabled = !queryInput.value.trim() || !selectedClientId;
}

// Send on click or Enter (Shift+Enter for newline)
sendBtn.addEventListener('click', handleSend);

queryInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSend();
  }
});

queryInput.addEventListener('input', () => {
  autoResizeInput();
  updateSendBtn();
});

function autoResizeInput() {
  queryInput.style.height = 'auto';
  queryInput.style.height = Math.min(queryInput.scrollHeight, 80) + 'px';
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

signInBtn.addEventListener('click', () => signIn());

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'AUTH_STATE_CHANGED' && message.authenticated) {
    init();
  }
  if (message.type === 'TAB_CHANGED') {
    // Active tab changed — refresh selected text check
    checkSelectedText();
  }
});

// Sync state from popup changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== 'session') return;

  if (changes.selected_client_id && changes.selected_client_id.newValue) {
    const id = changes.selected_client_id.newValue;
    const name = changes.selected_client_name?.newValue ||
      allClients.find(c => c.id === id)?.name || 'Unknown';
    if (id !== selectedClientId && allClients.some(c => c.id === id)) {
      selectClient(id, name);
    }
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function esc(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

init();
