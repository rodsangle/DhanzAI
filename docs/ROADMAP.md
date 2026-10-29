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

## Phase 4 — Platform distribution (this milestone)

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

⬜ Redis-backed shared rate limiting and job queue · ⬜ metrics/tracing (OpenTelemetry) ·
⬜ admin RBAC endpoints · ⬜ data-retention jobs · ⬜ encryption of message content at rest
(application-level) · ⬜ load tests · ⬜ Google/Apple sign-in · ⬜ offline mode (local history
cache, on-device models where hardware allows).
