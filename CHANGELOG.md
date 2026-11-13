# Changelog

## Unreleased

### Branch, archive and share chats (web 0.10.14+55, ChatGPT parity round 1)

- **Branch in new chat** on any finished reply: a new chat with the messages up to that reply.
- **Archive** from a chat's menu hides it from the history; Settings → Archived chats restores it.
- **Share chat** creates a revocable public read-only link to a frozen copy of the chat (no
  attachments, tool details or the owner's name); Settings → Shared links lists and revokes them.
- Backend package `app/conversation_extras` with its own tables (migration 0009); installed on the
  live server by `scripts/server/deploy_conversation_extras.py` (rehearsed: check, apply, routes,
  repeat, rollback).
- `replica/`: ChatGPT recon map, feature matrix and build plan.

### One chat box and previews (web 0.10.13+54)

- Chat · Photo · Video · Code selector in the message box. Photo and video requests are sent into the
  conversation so the generation card and result stay in its history; Code opens the coding
  workspace (replaces the separate "Continue in Codex" button).
- Finished photos and videos: a Preview chip opens them in the chat side panel (dialog on phones).
- The chat history sidebar can be hidden to a thin strip and shown again; the choice is remembered.

### GPT-5.5 / 5.6 / 6.x support

- The OpenAI adapter drops a refused temperature and sends `reasoning_effort: "none"` with tools
  when a model asks for it (learned per model from the HTTP 400 reply).
- A model that refuses a request before answering no longer fails the chat: the next model answers.
- `scripts/server/deploy_ai_engine.py` installs these files into the running API with a test and a
  rollback image; `upgrade_models.py` tests models the same way once the server has them.

### Newest AI models on the server

- `scripts/server/upgrade_models.py` switches the server to the newest chat and image models its
  own keys can use, after a live test request to each one (report-only unless `--apply`).
- ROG: `apps/rog_video_worker/setup_next_models.py` installs and tests Wan 2.2 TI2V-5B (video)
  and Z-Image-Turbo (photos) in a separate environment; the Wan 2.1 worker is unchanged.
- GPT-5 and later models are treated as able to read images; `luna` models count as low-cost.

### One Flutter app (web 0.10.12+53)

- `apps/dhanz_flutter` is now the app the live site runs (previously copied in
  `client_releases/0.10.0-updates`), with the Android, iOS, Windows and macOS projects.
- The live app gains the three themes and Follow system, and the public-account screens:
  email confirmation, two-step verification (shown only when the server supports it),
  Google/Apple sign-in where configured, linked accounts, account deletion for password-less
  accounts, and the admin "turn off two-step verification" action.
- Files created by the backend's document tools appear in chat like other generated files.
- The web-update workflow publishes only when started by hand from the Actions tab.

### Repository consolidation

- The production line (web releases 0.9.3–0.10.11, server updaters, assistant skills, Windows
  companion) is now on `main`.
- Removed the superseded 0.9.3–0.9.9 client copies and their build workflows; their builds remain
  available as GitHub releases.
- CI now fails when Flutter analysis, tests or the web build fail (they were hidden by a pipe).

### Themes

- Settings → Appearance → **Theme** offers three themes with live previews: **Midnight Gold**
  (deep navy and warm gold), **Arctic Light** (crisp daytime theme) and **Aurora Teal** (blue-green
  with mint and violet), plus **Follow system** (Arctic Light in light mode, Midnight Gold in dark mode).
- The choice is saved on the device (Windows, Android, browsers) and applied immediately.
- The previous Light / Dark / System setting carries over: Light → Arctic Light, Dark → Midnight
  Gold, System → Follow system. No other setting changes.
- All screens take their colours from one shared theme (buttons, inputs, cards, dialogs, menus,
  tables, tabs, chips, switches, code blocks). Text, borders and focus colours are checked for
  readable contrast; a few mockup shades were adjusted for that (Arctic blue, Aurora violet text).
- Following the theme concepts: the open conversation in the sidebar is highlighted in the theme's
  accent tint, and the message composer has a faint accent edge.

## 0.8.0

App version `0.8.0+8`. API version `0.8.0`.

### Public accounts

- Email verification by a 6-digit code. With `REQUIRE_EMAIL_VERIFICATION=true`, chats, files, the library, projects, memory, voice, reminders and Creative Studio stay locked until the address is confirmed. Accounts that already existed were marked verified by the migration.
- Two-step verification with authenticator apps: QR code and manual key, ten single-use recovery codes, a lockout after five wrong codes in fifteen minutes, and secrets encrypted at rest. Turning it on signs out other devices. Account deletion asks for a code. An administrator can reset a lost authenticator; that action is audited.
- Sign in with Google on Android and iOS, and Sign in with Apple on iOS. The server checks the ID token (signature, audience, issuer, expiry, nonce). The same verified email joins the existing account. Web and desktop Google sign-in, and Apple sign-in off iOS, are not in this release.

### Office documents from chat

- Dhanz can create Word, PDF, Excel, CSV and PowerPoint files and save them to the library.
- Chat and the library preview those files before download: spreadsheet grids, slide text, Word headings and paragraphs, and rendered PDF pages.
- Cells that look like formulas are stored as text. Charts, images inside slides, animations and spreadsheet formulas are not generated.

### Also in this release

- New chat opens a blank conversation.
- Dependency updates for the backend and GitHub Actions.

The published Windows installer on the README remains the 0.7.0 build (`desktop-0.7.0`) until the `v0.8.0` tag is pushed and the release workflow publishes new artifacts.
