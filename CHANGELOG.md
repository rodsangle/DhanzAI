# Changelog

## Unreleased

### Repository consolidation

- The production line (web releases 0.9.3–0.10.11, server updaters, assistant skills, Windows
  companion) is now on `main`. The live web app is built from `client_releases/0.10.0-updates`.
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
