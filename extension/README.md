# Callwen Browser Extension

Chrome extension for capturing documents, emails, and web content directly into your Callwen workspace.

## Features

- **Page capture** — save full pages, text selections, or linked files to a client's document library
- **Gmail integration** — extract structured email data (sender, subject, body)
- **Tax software detection** — recognizes Drake, Lacerte, UltraTax CS, ProConnect
- **QuickBooks detection** — recognizes QBO pages
- **Monitoring rules** — auto-detect pages matching domain, email, URL, or content patterns
- **Client matching** — associate captures with clients via email routing or company name
- **Tier-gated limits** — daily capture limits based on your Callwen subscription

## Setup

```bash
cd extension
npm install
npm run build
```

## Load in Chrome

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension/dist/` directory

## Development

```bash
npm run dev    # watch mode — rebuilds on file changes
```

After making changes, click the reload button on `chrome://extensions` to pick up the new build.

## Authentication

The extension authenticates via Clerk. Sign in at [callwen.com](https://callwen.com) in the same browser — the content script detects the session cookie and relays the JWT to the extension.

## Project Structure

```
extension/
├── manifest.json              # Manifest V3 config
├── webpack.config.js          # Build config (4 entry points)
├── src/
│   ├── background/            # Service worker (context menus, message routing)
│   ├── popup/                 # Popup UI (capture controls, client selector)
│   ├── sidepanel/             # Side panel (Quick Query — placeholder)
│   ├── content/               # Content script (auth relay, page metadata)
│   ├── parsers/               # Domain-specific page parsers
│   ├── services/              # API client, auth, capture, monitoring
│   ├── utils/                 # Config constants, Chrome storage helpers
│   └── assets/                # Extension icons
└── dist/                      # Build output (gitignored)
```
