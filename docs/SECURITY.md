# Security and privacy

## What is implemented (Phase 1)

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
| Audit log | Register, login, failed login, logout, account deletion (IP + timestamp); entries survive account deletion with the user link removed |
| Prompt injection | System prompt instructs the model to treat web/document/tool content as untrusted data that cannot change rules or authorize actions. Phase 1 has no tools, so model output cannot trigger actions |
| Privacy | Data export (`GET /users/me/export`), real account deletion (DB cascade), no analytics or third-party trackers in the app |
| Containers | Non-root user, no secrets baked into images, healthcheck |

## Known limitations (to address before a public launch)

* Rate limiting is per process. With several API replicas use a shared limiter (Redis, or the
  reverse proxy / API gateway).
* Message content is protected by database access controls and disk/volume encryption of your
  hosting provider, not by application-level encryption.
* No email verification or password reset flow yet.
* No MFA; no Google/Apple sign-in yet.
* Conversations are sent to whichever AI provider handles the request; their data-retention
  policies apply. Use Ollama (`local_first`) to keep data on your own hardware.
* Audit-log retention and data-retention settings are not yet configurable.

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
