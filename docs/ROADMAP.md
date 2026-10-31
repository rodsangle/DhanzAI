# DHANZ AI — Roadmap and implementation status

Legend: ✅ implemented and tested · 🟡 partially implemented · ⬜ not started

## Creative Studio — 0.7 update

| Feature | Status | Notes |
|---|---|---|
| Image generation and natural-language reference editing | 🟡 | OpenAI-compatible adapter, prompt/ratio/quality/format controls; API and widget tests use simulated services; live verification pending |
| Asynchronous video generation | 🟡 | Runway Gen-4.5 text/image-to-video, persisted tasks, polling, cancel, MP4; live verification pending; retired Sora API not exposed |
| Private creation gallery, previews, downloads and explicit sharing | 🟡 | Flutter studio on Windows/Android/iOS/web; widget tests and web compilation checks; native playback/share need devices |
| Credit reservations, settlement/refunds, monthly plan allowances | ✅ | Server-side ledger, idempotency and concurrent requests tested on SQLite; PostgreSQL covered by CI configuration |
| Payment checkout / purchased credit packs | ⬜ | Admin grants and per-user plan allowances exist; no payment gateway or webhook handler |
| Private cloud media storage / expiring preview links / cleanup | 🟡 | Encrypted S3-compatible adapter and deletion outbox; simulated storage contract tests; live bucket verification pending |
| Safety screening, consent, reports, admin takedown | 🟡 | Fail-closed prompt/reference and image-output screening, native provider video checks; no independent video-frame moderation or rights verification |
| Dedicated image upscaling / generated video audio | ⬜ | Generative enhancement exists; unsupported controls are not offered |

See [Creative Studio](CREATIVE_STUDIO.md) for configuration, architecture, verification and limitations.

Nothing marked ⬜ exists in the code base as a mock or placeholder screen; the app only shows
features that work.

## Phase 1 — Working MVP

| Feature | Status | Notes |
|---|---|---|
| FastAPI backend, PostgreSQL schema + Alembic migration | ✅ | Verified on PostgreSQL 16 + pgvector and SQLite |
| Email/password auth, rotating refresh tokens, logout | ✅ | Reuse detection revokes the session family |
| OpenAI, Anthropic, Gemini, Ollama providers (streaming) | ✅ | Wire formats covered by tests; live keys required to use them |
| Model orchestration (task/policy/cost routing, fallback) | ✅ | Keyword-based task detection |
| Chat streaming over SSE and WebSocket | ✅ | Flutter uses SSE |
| Conversation history: list, search, rename, pin, delete | ✅ | |
| Regenerate, edit-and-resend, stop generation | ✅ | Stopped/partial replies are saved |
| Export conversation (Markdown, TXT) | 🟡 | Shown in a dialog with *Copy*; saving to a file and **PDF** export come in Phase 3 |
| Data export (JSON) and account deletion | ✅ | |
| Flutter app: welcome, sign-in/up, chat, history, model selection, settings/privacy, profile | ✅ | Light/dark themes, responsive layouts |
| Markdown rendering + code syntax highlighting, copy buttons | ✅ | |
| Logo and app icons (Android, iOS, Windows, macOS, web) | ✅ | `scripts/generate_icon.py` |
| CI: lint, unit tests, Postgres e2e, Docker build, Flutter analyze/test | ✅ | |
| Release builds: APK/AAB, Windows installer + zip, iOS (unsigned or signed IPA) | ✅ | All four platforms built on GitHub runners (manual runs, Oct 2026); signing needs the secrets in RELEASE.md |
| Google / Apple sign-in | 🟡 | See "Public platform" below: server-verified; Google on Android and iOS, Apple on iOS |
| Projects / workspaces | ⬜ | Phase 3 |

## Phase 2 — Internet intelligence (this milestone)

| Feature | Status | Notes |
|---|---|---|
| Web search via search APIs (Brave, Tavily, SearXNG) | ✅ | Configure one with `SEARCH_PROVIDER`; adapters tested against recorded API responses |
| Automatic "does this need the web?" decision + per-chat web mode (Auto / Always / Off) | ✅ | Keyword heuristic; links pasted in a message are always read |
| Polite, safe page fetching (robots.txt, per-host rate limit, no paywall/login bypass, SSRF protection) | ✅ | |
| Main-content extraction with title, site, author and publication date | ✅ | HTML and plain text; PDFs come with Phase 3 document support |
| Multi-source answers with numbered `[n]` citations, clickable source cards, publication and retrieval dates | ✅ | Pages that cannot be read fall back to the search engine's snippet |
| Webpage summarisation ("summarise https://…") | ✅ | |
| News research | 🟡 | News-flavoured queries use the provider's news vertical; there is no dedicated news screen |
| Source reliability | 🟡 | The model is told to flag conflicts and dates; there is no automated per-site reliability score |
| Knowledge library: add pages, browse, preview, search, delete | ✅ | Private per user; included in data export and account deletion |
| RAG: chunking, embeddings in pgvector, hybrid keyword + semantic retrieval used in chat | ✅ | Semantic search needs `EMBEDDING_PROVIDER`; keyword search works without it |
| Auto-saving researched pages to the library (user opt-out) | ✅ | |
| LangGraph research flow | ⬜ | The pipeline is a plain async function; a graph adds value once tools need approvals (Phase 3) |
| Approximate-nearest-neighbour (HNSW) index | ⬜ | Exact vector search per user is fast at personal-library scale; add an index per embedding model when libraries get large |

## Phase 3 — Advanced assistant

| Feature | Status | Notes |
|---|---|---|
| File uploads: PDF, DOCX, XLSX, PPTX, CSV/TSV, text, Markdown, source code, images | ✅ | Real type checked (not just the name), size limit, zip-bomb and password-protection checks; legacy .doc/.xls/.ppt rejected with a clear message |
| Malware scanning | 🟡 | ClamAV (clamd) integration, fail-closed when configured (`docker compose --profile scan`); without it files are stored as `not_scanned` |
| Ask questions about attached documents, compare documents, summarise | ✅ | Short files given whole, long files by opening + most relevant passages; each file is a citable `[n]` source |
| Spreadsheet analysis | ✅ | Row/column counts and exact per-column sum/mean/min/max computed server-side, plus the first 200 rows |
| Images / technical drawings | ✅ | Sent to a vision-capable model (OpenAI, Claude, Gemini, LLaVA-type Ollama models); routing refuses non-vision models |
| Scanned PDFs (OCR) | 🟡 | Optional local Poppler + Tesseract when `OCR_ENABLED=true`; no external OCR service. Tests simulate the engines; recognition quality needs a server with both installed ([OCR.md](OCR.md)) |
| Uploaded files in the knowledge library (search, download, move to project, delete) | ✅ | Files are private; downloads are always `attachment` + `nosniff` |
| Generate downloadable files | 🟡 | Conversations can be saved as PDF, Markdown or text; generating new reports/spreadsheets as files is not implemented |
| Project workspaces | ✅ | Group chats and documents, standing instructions added to the prompt, project chats only search that project's documents |
| Opt-in long-term memory | ✅ | Off by default; "Remember that …" in chat or manual entries; view, edit, delete, delete all, disable; included in data export |
| Voice assistant | ✅ | Record → server speech-to-text (OpenAI-compatible, e.g. Whisper) → answer → device text-to-speech; voice picker and speed; automatic end-of-speech detection; hands-free loop; optional "Hey Dhanz" wake phrase |
| Background / always-on wake word | ⬜ | Deliberately not done: the microphone is only used while the Voice screen is open, as Android and iOS require |
| Tools (calculator, unit conversion, email drafting, calendar, reminders) | ✅ | Delivered in the "Assistant tools" milestone below |

## Phase 4 — Platform distribution

| Feature | Status | Notes |
|---|---|---|
| Replies survive leaving the app | ✅ | Each reply runs as a server task, not tied to the connection; the app follows it again on return or reconnect |
| Explicit Stop | ✅ | `POST /conversations/{id}/stop`; works across server workers (database flag checked every second) |
| Push notifications when an answer is ready (Android FCM, iOS APNs) | 🟡 | Server side tested against mocked FCM/APNs; native code written but **not compiled or run on a device in this milestone** (no Android SDK/Xcode in the build environment). Needs a Firebase project and an APNs key; notification text never contains the question or answer |
| Windows/macOS/Linux: system tray, minimize to tray, desktop notifications | 🟡 | `window_manager`, `tray_manager`, `local_notifier`; Dart side tested; not yet tried on a real Windows desktop |
| Drag-and-drop files into the chat (desktop) | ✅ | Same upload checks as the attach button |
| In-app updates | 🟡 | Backend `GET /app/updates` + release manifest `latest.json`. Windows downloads the installer, checks SHA-256, runs it silently and restarts; other platforms open the download/store page. Not exercised end-to-end against a real release yet |
| Windows code signing | 🟡 | Release workflow signs the exe and installer when `WINDOWS_CERT_PFX_BASE64` is set; needs a purchased certificate |
| Android / iOS release signing | 🟡 | Via secrets (since Phase 1) |
| macOS build | 🟡 | Unsigned `.app` zip from CI; signing and notarization not set up |
| Store listings (Play, App Store, Microsoft Store) | ⬜ | Needs developer accounts, privacy forms and screenshots |
| Linux packages | ⬜ | The app runs on Linux (`flutter build linux`) but is not packaged |

## Phase 5 — Production readiness

| Area | Feature | Status | Notes |
|---|---|---|---|
| Security | Sessions list, sign out one device or all others | ✅ | Access tokens carry their session; revoking it locks them out immediately, not after 15 minutes |
| Security | Change password (signs out other devices) | ✅ | |
| Security | Password reset by emailed one-time code | ✅ | Needs SMTP; codes are single-use, expire in 30 min, burn after 5 wrong guesses; the API never reveals whether an email is registered |
| Security | Per-account login lockout | ✅ | After 5 failures in 15 minutes (configurable), on top of per-IP limits |
| Security | Shared rate limits (Redis) | ✅ | `REDIS_URL`; falls back to per-process limits if Redis is down |
| Security | Request size limits, extra headers (CSP, CORP) | ✅ | |
| Security | Closed registration for private servers; first account is the administrator | ✅ | `ALLOW_REGISTRATION=false` |
| Security | Email verification, MFA, Google/Apple sign-in | ✅ | See "Public platform" below |
| Security | Application-level encryption of message content | ⬜ | Rely on encrypted volumes; app-level encryption would disable server-side search |
| Privacy | Auto-delete old conversations (7/30/90/365 days) | ✅ | Per user, in Settings |
| Privacy | Temporary chats | ✅ | No memory, no library indexing, deleted after 24 h |
| Privacy | Audit-log retention, expired-token clean-up | ✅ | Hourly maintenance job (`python -m app.cli maintenance` to run it by hand) |
| Admin | Usage statistics, account list, deactivate/reactivate, roles, audit log | ✅ | API + app screen; `python -m app.cli promote <email>` |
| Monitoring | Request IDs, JSON logs, Prometheus metrics (HTTP, replies, tokens, push, clean-up) | ✅ | `/metrics` only with `METRICS_TOKEN`; aggregated across workers |
| Monitoring | Distributed tracing (OpenTelemetry) | ⬜ | Request IDs are propagated in logs and the `X-Request-ID` header |
| Performance | Response compression, DB pool settings, password hashing off the event loop | ✅ | |
| Performance | Load-test script | ✅ | `tests/load/load_test.py`; see TESTING.md for measured numbers |
| Pipelines | Coverage gates, dependency audit, CodeQL, Dependabot | ✅ | |
| Pipelines | Signed-provenance container image on GHCR, production compose with automatic HTTPS and nightly backups | ✅ | `deploy/` — see DEPLOY.md |
| Offline | Offline history cache, on-device models | ⬜ | |
| Tools | Calculator, unit conversion, calendar, reminders, email drafting | ✅ | See below |

## Assistant tools (this milestone, originally Phase 3b)

Dhanz calls tools through each provider's native function calling (OpenAI and compatible APIs,
Anthropic, Gemini, and Ollama models that support tools). Models without function calling answer
as before.

| Tool | Status | Notes |
|---|---|---|
| Calculator | ✅ | Exact, safe evaluator (no code execution): arithmetic, powers, roots, logs, trigonometry |
| Unit conversion | ✅ | Length, mass, volume (incl. cooking), area, speed, time, data, energy, pressure, power, temperature |
| World time and date arithmetic | ✅ | Any IANA time zone; days/weekdays between dates; adding days, months, years |
| Reminders | ✅ | "Remind me to … tomorrow at 9" resolved in the user's time zone (the app sends its UTC offset); push notification when due (desktop: system notification while the app runs); Reminders screen |
| Calendar | 🟡 | Reminders/events export as `.ics` (*Add to calendar*) for any calendar app. No direct Google/Outlook calendar access (would need OAuth sign-in to those services) |
| Email drafting | ✅ | Draft card with *Open in email app* and *Copy*; Dhanz never sends email — the user reviews and sends it from their own app |
| Approval for external actions | ✅ | No tool acts outside DHANZ AI; anything leaving the app is a button the user presses |
| Native tool-calling verified against live provider APIs | 🟡 | Wire formats are tested against recorded examples, not against the live services in this milestone |


## Public platform

The goal from here: a public service anyone can download and sign up for, with Free / Plus / Pro
plans. Work is split into milestones; each is shipped and tested before the next starts.

### Milestone A — public accounts (this milestone)

| Feature | Status | Notes |
|---|---|---|
| Email verification by 6-digit code | ✅ | Sent at sign-up when SMTP is configured. `REQUIRE_EMAIL_VERIFICATION=true` locks chats, files, library, projects, memory, voice, reminders and Creative Studio until confirmed. Accounts that existed before were marked verified by the migration |
| Two-step verification (TOTP authenticator apps) | ✅ | QR code + manual key; 10 single-use recovery codes; one code can't be reused; 5 wrong codes per 15 min per account; secrets encrypted at rest (AES-256-GCM, `DATA_ENCRYPTION_KEY`); turning it on signs out other devices; account deletion asks for a code |
| Admin reset of a lost authenticator | ✅ | Admin screen → user menu; audited |
| Sign in with Google | 🟡 | Server verifies the ID token (signature via Google's keys, audience, issuer, expiry, nonce). App: Android and iOS. **Web and desktop not yet** (web needs Google's own button; Windows has no Google SDK) |
| Sign in with Apple | 🟡 | Server-verified like Google, including Apple's hashed nonce. App: iOS. **Android/web need a Services ID and a redirect page — not built yet** |
| Linking and account safety | ✅ | Same verified email → same account. If an address was registered with a password but never confirmed, a Google/Apple sign-in for it removes that password and signs out its sessions (stops pre-registration takeover). Unlink refuses to remove the last way to sign in |
| Bot protection on sign-up (CAPTCHA / app attestation) | ⬜ | Today: per-IP rate limits, per-account lockout, email verification. Cloudflare Turnstile (web) and Play Integrity / App Attest (phones) planned |

### Milestone B — subscriptions and usage limits (next)

| Feature | Status |
|---|---|
| Plans (Free / Plus / Pro) stored in the database: price, message quota, allowed models, upload/storage limits, features | ⬜ |
| Per-user usage metering and quota enforcement (messages, tokens, uploads, research) with clear "limit reached" UI | ⬜ |
| AI cost tracking per provider/model (price table maintained by the admin) and spending caps | ⬜ |
| Stripe Checkout + customer portal, verified by signed webhooks (web and desktop) | ⬜ |
| Google Play Billing and Apple StoreKit 2 purchases, verified server-side (RTDN / App Store Server Notifications) | ⬜ |
| Entitlements derived only from verified payment events | ⬜ |

Needs: a Stripe account, a Google Play developer account with a merchant profile, an Apple
developer account with Paid Apps agreement.

### Milestone C — administrator dashboard

| Feature | Status |
|---|---|
| Web dashboard (Flutter web, admin role + two-step verification required) | ⬜ |
| Users, active users, subscriptions, revenue and AI cost charts | 🟡 (counts and usage exist in the app's admin screen) |
| Plan, quota, provider and model configuration without code changes | ⬜ |
| Abuse reports from users, review queue, suspension with reason | 🟡 (deactivate/reactivate exists) |
| Announcements shown in the apps | ⬜ |
| Error and performance views (from the existing Prometheus metrics) | ⬜ |
| Release management (publish `latest.json` from the dashboard) | ⬜ |
| Support access to private chats | Deliberately not built: admins cannot read conversations. Any future support access must be user-granted, time-limited and audited |

### Milestone D — launch readiness

| Feature | Status |
|---|---|
| Web app build in CI and hosting (behind the same Caddy) | 🟡 (`flutter build web` compiles; not yet published) |
| Content safety: provider moderation endpoints on input/output, refusal UI | ⬜ |
| Prompt-injection defences for web pages and documents | 🟡 (fetched text is passed as quoted source material and tools need no approval because none act externally; formal tests to add) |
| Privacy policy, terms of service, in-app links, store privacy forms | ⬜ (text must come from the operator / a lawyer) |
| Store listings (Play, App Store, Microsoft Store) | ⬜ |
| Object storage (S3-compatible) for uploads | ⬜ (local volume today) |
| Background worker queue (Redis) for indexing and notifications | 🟡 (in-process tasks today) |
