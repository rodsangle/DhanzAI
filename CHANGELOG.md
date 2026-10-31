# Changelog

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
