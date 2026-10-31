# Security and privacy

## What is implemented

| Area | Implementation |
|---|---|
| Passwords | Argon2id (`argon2-cffi` defaults), transparent rehash on login; min 10 chars, must mix letters with digits/symbols; constant-time dummy verify for unknown emails |
| Sessions | 15-min HS256 JWT access tokens; opaque 384-bit refresh tokens stored only as SHA-256; rotated on every use; reuse of a rotated token revokes the entire session family; logout revokes the family |
| Authorization | Every conversation/message query is scoped to the authenticated owner; other users' IDs return 404 (no existence oracle); roles stored (`user`/`admin`) for future admin endpoints |
| Input validation | Pydantic schemas with length limits; message size cap (`MAX_MESSAGE_CHARS`); LIKE wildcards escaped in search |
| Rate limiting | Per-IP on auth endpoints, per-user on chat (in-process; see limitations) |
| Transport | Deploy behind TLS. Production adds HSTS. Android release builds forbid cleartext; iOS ATS only allows local-network HTTP for development |
| Headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; CORS allow-list; no cookies (bearer tokens) |
| Secrets | Provider keys and `JWT_SECRET` only in server environment; app refuses to start in production with a weak secret or SQLite; `.env`, keystores and signing files are git-ignored |
| Client storage | Tokens in Keychain (iOS/macOS), Android Keystore-backed storage, Windows DPAPI via `flutter_secure_storage` |
| Errors | Raw provider errors are logged server-side and replaced with a generic message for clients |
| Audit log | Register, login (with method), failed login, two-step challenges and failures, identity linking, email confirmation, logout, account deletion (IP + timestamp); entries survive account deletion with the user link removed |
| Prompt injection | Retrieved web/library text is placed in a `<sources>` block labelled as untrusted data; the system prompt forbids following instructions inside it. Dhanz's tools have no effect outside DHANZ AI (see below), which limits what injected text could achieve |
| Server-side fetching (Phase 2) | Only http/https on ports 80/443; URLs with credentials refused; every DNS answer must be a public address (blocks localhost, private ranges, link-local/cloud metadata) and this is re-checked on every redirect; 2 MB cap; HTML/text only; no cookies or auth headers sent |
| Responsible crawling | Fetches only pages a user asked about or a search returned (no crawling); honours robots.txt for `DhanzAI-Research` (robots.txt unreachable because of a server or network error = disallowed); spaces requests per host; pages returning 401/402/403 are reported as requiring a login/subscription and are never worked around |
| File uploads (Phase 3) | Size cap (`MAX_UPLOAD_MB`); type decided by content signatures, not the filename; Office files checked for zip bombs and encryption; legacy binary Office formats refused; filenames sanitised; bytes stored under random keys outside the web root; optional ClamAV scanning that fails closed; downloads only as `application/octet-stream` attachments with `nosniff`; parsing runs off the event loop and errors are contained |
| Images and vision | Images are only sent to the model handling that message, and only to vision-capable models |
| Memory | Off by default; only saved on explicit request ("Remember that …") or manual entry; fully viewable, editable and deletable; never used while disabled |
| Voice | Audio is recorded only while the Voice screen is open, uploaded for transcription, and the temporary file is deleted from the device; nothing is recorded in the background |
| Knowledge privacy | Library documents and chunks are scoped to their owner in every query (including vector search); deleted with the account; included in data export |
| Privacy | Data export (`GET /users/me/export`), real account deletion (DB cascade), no analytics or third-party trackers in the app |
| Push notifications (Phase 4) | Notification text is generic ("Dhanz finished your answer") so nothing private appears on a locked screen; the payload carries only conversation/message IDs, which are useless without the user's session. Device tokens belong to one account at a time, are removed on sign-out and when FCM/APNs report them invalid. FCM service-account and APNs keys stay on the server |
| App updates (Phase 4) | Only `https://` download URLs from the server's manifest are offered; the Windows installer is verified against the SHA-256 in the manifest before it runs, and a mismatching download is deleted. Release builds can be Authenticode-signed |
| Background replies (Phase 4) | Replies continue after a disconnect but are still bound to the user who started them; only the conversation owner can stop them |
| Sessions (Phase 5) | Each access token carries its session (refresh-token family); signing a device out, "sign out everywhere", a password change or reset, deactivation all take effect on the next request instead of after the 15-minute token lifetime. Users see their devices and can revoke them |
| Brute force (Phase 5) | Per-IP limits plus a per-account lockout (5 failures / 15 min by default) applied identically to unknown emails; limits are shared through Redis across workers |
| Password reset (Phase 5) | 10-character one-time code by email (≈50 bits), stored as SHA-256, valid 30 minutes, single use, invalidated after 5 wrong guesses; requests answer identically whether or not the account exists and the email is sent in the background; a reset signs out every session |
| Administration (Phase 5) | Role checked from the database on every admin request; admins cannot demote or deactivate themselves; every admin change is audit-logged; first account on a new server is the administrator, `ALLOW_REGISTRATION=false` closes sign-up |
| Request limits & headers (Phase 5) | JSON bodies capped (`MAX_REQUEST_KB`), uploads by their own limits, before the body is read; production adds `Content-Security-Policy: default-src 'none'` and `Cross-Origin-Resource-Policy` |
| Supply chain (Phase 5) | CI runs `pip-audit` and CodeQL; Dependabot proposes updates; release images carry build provenance and an SBOM |
| Assistant tools | Tool arguments come from the model and are validated like any user input (the calculator parses arithmetic only — no code execution; time zones, dates and units are checked). Tools act only on the user's own data: reminders are scoped to the user, email drafts are handed to the user's email app, and generated Office files are stored in that user's library. Preview reads those same bytes and is limited to the owner, like download. Spreadsheet cells that look like formulas are saved and shown as text so opening the file does not run them. PDF preview pages are rendered on the server. Dhanz cannot send email. Worst case for a prompt injection through a web page or document: an unwanted reminder, a draft, or a file the user sees before deciding to download it |
| Email verification (public accounts) | 6-digit code by email (Argon2id stored), valid 60 minutes, burnt after 5 wrong guesses, 3 emails per hour per account. With `REQUIRE_EMAIL_VERIFICATION=true` every content route (chats, files, library, projects, memory, voice, reminders, Creative Studio) returns 403 until confirmed. Signed Creative Studio media links stay usable without a session |
| Two-step verification (public accounts) | RFC 6238 TOTP (30 s, 6 digits, ±1 step), secret encrypted at rest with AES-256-GCM (key from `DATA_ENCRYPTION_KEY` via HKDF); a code is accepted once only; 10 recovery codes (~60 bits, Argon2id stored, single use). Sign-in returns a 5-minute challenge token that cannot be used as an access token; 5 wrong codes per 15 min lock the second step for that account. Turning it on signs out other devices; turning it off, replacing recovery codes and deleting the account need a current code |
| Google / Apple sign-in (public accounts) | The server verifies each ID token itself: RS256 signature against the provider's published keys (cached, refetched on key rotation), issuer, audience = our client IDs, expiry, and nonce when sent (Apple's SHA-256 form too). Accounts are found by the provider's stable `sub`, not the email. A verified email matching an existing account links to it; if that account's address was never confirmed, its password and sessions are removed (an impostor who pre-registered the address loses access). Two-step verification still applies. The last sign-in method cannot be unlinked |
| Containers | Non-root user, no secrets baked into images, healthcheck |

## Known limitations (to address before a public launch)

* Without `REDIS_URL`, rate limits and the login lockout are counted per worker process.
* Message content is protected by database access controls and disk/volume encryption of your
  hosting provider, not by application-level encryption.
* No CAPTCHA or app attestation on sign-up yet: rely on rate limits and email verification.
* Google sign-in in the app works on Android and iOS; Apple on iOS. Web and desktop users sign in
  with email and password for now.
* If `DATA_ENCRYPTION_KEY` (or, without it, `JWT_SECRET`) changes, stored two-step secrets can no
  longer be read; affected users need an admin reset.
* Self-service password reset needs SMTP. Without it, the server administrator can set a new
  password with `python -m app.cli set-password <email>`.
* DNS rebinding: addresses are checked before connecting, but a hostile DNS server could
  answer differently at connect time. Run the API with egress restricted to the public
  internet (no route to internal networks) for defence in depth.
* Search queries go to the configured search provider (Brave/Tavily) under its privacy
  policy; use self-hosted SearXNG to avoid that.
* Conversations are sent to whichever AI provider handles the request; their data-retention
  policies apply. Use Ollama (`local_first`) to keep data on your own hardware.
* Without ClamAV configured, uploads are stored unscanned (marked `not_scanned`). Enable the
  `scan` profile for any multi-user deployment.
* Uploaded files are stored unencrypted on the server volume; use encrypted disks/volumes.
* Voice recordings are sent to the configured speech-to-text provider (OpenAI or your own Whisper server).
* Reminder notifications show the reminder text, which can appear on a locked screen.
* Push notifications pass through Google (FCM) and Apple (APNs). They only contain a generic
  text and IDs.
* The update manifest's checksum protects against corrupted or swapped downloads, but the
  manifest itself is trusted because it comes over TLS from your server. Code signing (Windows
  certificate, Apple notarization) is the stronger guarantee; set it up before a public release.

## Operating securely

1. Generate `JWT_SECRET` with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. Run with `APP_ENV=production` (disables `/docs`, enables HSTS, enforces secret/DB checks).
3. Terminate TLS at a reverse proxy (Caddy, nginx, a cloud load balancer) and set
   `FORWARDED_ALLOW_IPS` to the proxy address so client IPs are correct for rate limiting.
4. Restrict `CORS_ORIGINS` to origins you serve (native apps don't need CORS).
5. Keep provider keys in your platform's secret manager; rotate them if leaked.
6. Back up PostgreSQL and test restores.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository rather than a public issue.
