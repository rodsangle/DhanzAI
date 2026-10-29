# DHANZ AI — Roadmap and implementation status

Legend: ✅ implemented and tested · 🟡 partially implemented · ⬜ not started

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
| Release builds: APK/AAB, Windows installer + zip, iOS (unsigned or signed IPA) | 🟡 | Workflows written; they have not been run on GitHub runners yet |
| Google / Apple sign-in | ⬜ | Phase 5 (needs OAuth client IDs and Apple developer account) |
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
| Scanned PDFs (OCR) | ⬜ | Detected and reported honestly; text recognition is not implemented |
| Uploaded files in the knowledge library (search, download, move to project, delete) | ✅ | Files are private; downloads are always `attachment` + `nosniff` |
| Generate downloadable files | 🟡 | Conversations can be saved as PDF, Markdown or text; generating new reports/spreadsheets as files is not implemented |
| Project workspaces | ✅ | Group chats and documents, standing instructions added to the prompt, project chats only search that project's documents |
| Opt-in long-term memory | ✅ | Off by default; "Remember that …" in chat or manual entries; view, edit, delete, delete all, disable; included in data export |
| Voice assistant | ✅ | Record → server speech-to-text (OpenAI-compatible, e.g. Whisper) → answer → device text-to-speech; voice picker and speed; automatic end-of-speech detection; hands-free loop; optional "Hey Dhanz" wake phrase |
| Background / always-on wake word | ⬜ | Deliberately not done: the microphone is only used while the Voice screen is open, as Android and iOS require |
| Tools (calculator, unit conversion, email drafting, calendar, reminders) | ⬜ | Moved to Phase 3b: needs provider tool-calling and an approval step for any external action |

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

## Phase 5 — Production readiness (this milestone)

| Area | Feature | Status | Notes |
|---|---|---|---|
| Security | Sessions list, sign out one device or all others | ✅ | Access tokens carry their session; revoking it locks them out immediately, not after 15 minutes |
| Security | Change password (signs out other devices) | ✅ | |
| Security | Password reset by emailed one-time code | ✅ | Needs SMTP; codes are single-use, expire in 30 min, burn after 5 wrong guesses; the API never reveals whether an email is registered |
| Security | Per-account login lockout | ✅ | After 5 failures in 15 minutes (configurable), on top of per-IP limits |
| Security | Shared rate limits (Redis) | ✅ | `REDIS_URL`; falls back to per-process limits if Redis is down |
| Security | Request size limits, extra headers (CSP, CORP) | ✅ | |
| Security | Closed registration for private servers; first account is the administrator | ✅ | `ALLOW_REGISTRATION=false` |
| Security | Email verification, MFA, Google/Apple sign-in | ⬜ | |
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
| Tools | Calculator, unit conversion, calendar, reminders, email drafting | ⬜ | Still open from Phase 3b |
