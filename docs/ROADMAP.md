# DHANZ AI — Roadmap and implementation status

Legend: ✅ implemented and tested · 🟡 partially implemented · ⬜ not started

Nothing marked ⬜ exists in the code base as a mock or placeholder screen; the app only shows
features that work.

## Phase 1 — Working MVP (this milestone)

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

## Phase 2 — Internet intelligence

⬜ Search API integration (e.g. Brave, Bing, Tavily, SearXNG — pluggable) ·
⬜ fetcher that honours `robots.txt`, rate limits per host, never bypasses paywalls/logins ·
⬜ readability extraction · ⬜ chunking + embeddings into pgvector · ⬜ hybrid retrieval ·
⬜ answers with clickable citations, publication/retrieval dates and source reliability notes ·
⬜ "Web research" screen and **Knowledge library** screen · ⬜ LangGraph research flow.

## Phase 3 — Advanced assistant

⬜ Voice: speech-to-text, text-to-speech, voice picker/speed, hands-free mode where the OS allows,
optional "Hey Dhanz" wake phrase (foreground-only on iOS/Android per platform rules) ·
⬜ file uploads (PDF, DOCX, XLSX, PPTX, CSV, images, code) with malware scanning, extraction,
Q&A, comparison, report generation · ⬜ opt-in long-term memory (view/edit/delete/disable) ·
⬜ projects/workspaces · ⬜ tools (calculator, unit conversion, email drafting, calendar,
reminders) with explicit user approval for any external action · ⬜ PDF export and file saving.

## Phase 4 — Platform distribution

🟡 Windows installer (Inno Setup script + CI) — ⬜ code signing, ⬜ auto-update, ⬜ system tray /
minimize-to-tray, ⬜ drag-and-drop, ⬜ desktop notifications · ⬜ push notifications (FCM/APNs) ·
🟡 Android signing via secrets · 🟡 iOS signing via secrets · ⬜ store listings.

## Phase 5 — Production readiness

⬜ Redis-backed shared rate limiting and job queue · ⬜ metrics/tracing (OpenTelemetry) ·
⬜ admin RBAC endpoints · ⬜ data-retention jobs · ⬜ encryption of message content at rest
(application-level) · ⬜ load tests · ⬜ Google/Apple sign-in · ⬜ offline mode (local history
cache, on-device models where hardware allows).
