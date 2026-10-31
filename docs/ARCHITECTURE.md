# DHANZ AI — System Architecture

> Your World. Your Knowledge. Your AI.

This document describes the target architecture for all phases and marks what exists today
(**Phases 1–3**) versus what is planned. See [ROADMAP.md](ROADMAP.md) for the phase plan and the
list of features that are not implemented yet.

## 1. Overview

```
┌──────────────────────────── Clients (Flutter, one codebase) ────────────────────────────┐
│  Windows 10/11 (.exe installer)   Android (.apk/.aab)   iPhone/iPad (.ipa)   macOS (later) │
│  Riverpod state · GoRouter navigation · flutter_secure_storage (Keychain/Keystore/DPAPI) │
└───────────────┬──────────────────────────────────────────────────────────┬──────────────┘
                │ HTTPS: REST + Server-Sent Events (streaming)             │ WSS (optional)
                ▼                                                          ▼
┌───────────────────────────────── FastAPI backend (/backend) ─────────────────────────────┐
│ auth (JWT access + rotating refresh)   users/privacy   conversations   chat streaming    │
│ rate limiting · security headers · audit log · input validation · CORS                   │
│                                  │                                                       │
│                    ┌─────────────▼──────────────┐      ┌───────────────────────────────┐ │
│                    │ AI engine (/ai_engine)      │      │ Knowledge engine              │ │
│                    │ Orchestrator: routing,      │      │ web search · fetch (robots)   │ │
│                    │ fallback, prompts           │      │ extraction · embeddings · RAG │ │
│                    │ Providers: OpenAI ·         │      └───────────────┬───────────────┘ │
│                    │ Anthropic · Gemini · Ollama │                      │                 │
│                    └─────────────┬──────────────┘                      │                 │
└──────────────────────────────────┼─────────────────────────────────────┼─────────────────┘
                                   ▼                                     ▼
                     Cloud model APIs / local Ollama        PostgreSQL 16 + pgvector · Redis
```

**Key principle:** provider API keys live only on the backend. The apps authenticate users and
talk to the DHANZ AI API; they never contain or see an OpenAI/Anthropic/Gemini key.

## 2. Repository layout

| Path | Contents | Status |
|---|---|---|
| `apps/dhanz_flutter` | Flutter app for Windows, Android, iOS (+ macOS/web scaffolding) | Phase 1 |
| `backend` | FastAPI service, SQLAlchemy models, Alembic migrations, tests | Phase 1 |
| `ai_engine` | `dhanz_ai` Python package: provider adapters + orchestrator | Phase 1 |
| `knowledge_engine` | `dhanz_knowledge` package: search APIs, safe fetching, extraction, embeddings, ranking, research pipeline | Phase 2 |
| `database` | PostgreSQL init scripts (pgvector, pg_trgm) | Phase 1 |
| `tests/e2e` | Black-box smoke test against a running API | Phase 1 |
| `scripts` | Icon generator, Windows installer script | Phase 1 |
| `.github/workflows` | CI (lint/test/Postgres/Docker/Flutter) and release builds | Phase 1 |
| `docs` | Architecture, install, testing, security, release | Phase 1 |

## 3. Backend (`backend/app`)

| Module | Responsibility |
|---|---|
| `main.py` | App factory, lifespan (DB engine, orchestrator), CORS, security headers |
| `core/config.py` | Typed settings from environment; refuses weak secrets / SQLite in production |
| `core/security.py` | Argon2id password hashing, JWT access tokens, opaque refresh tokens (SHA-256 at rest) |
| `core/rate_limit.py` | Sliding-window limits (auth per IP, chat/uploads per user, login lockout per account), shared through Redis when `REDIS_URL` is set |
| `core/observability.py` | Request IDs, JSON logging, Prometheus metrics, request-size limits (pure ASGI middleware, streaming-safe) |
| `services/maintenance.py` | Hourly clean-up: conversation retention, temporary chats, expired sessions/reset codes, old audit entries |
| `services/mailer.py` | SMTP for password-reset and email-verification codes |
| `services/accounts.py`, `core/mfa.py` | Email codes, TOTP two-step verification (encrypted secrets, recovery codes), finishing a sign-in |
| `services/oauth.py` | Verifies Google / Apple ID tokens against the providers' published keys |
| `services/assistant_tools.py`, `services/office_files.py`, `services/file_preview.py` | Tools Dhanz can call: calculator, units, world time, date maths, reminders, email drafts, and Word/PDF/Excel/CSV/PowerPoint files saved to the library. Preview reads the stored file (grids, slides, headings, rendered PDF pages) for the owner only |
| `services/reminders.py` | Due-reminder delivery (claimed once across workers) and `.ics` export |
| `cli.py` | `python -m app.cli promote|demote|set-password|maintenance` |
| `models/` | `users`, `refresh_tokens`, `conversations`, `messages`, `audit_logs` |
| `services/auth_service.py` | Token issue, rotation, reuse detection (revokes the whole session family) |
| `services/chat_service.py` | Turn preparation (send / edit-and-resend / regenerate), research phase, history building, streaming + persistence |
| `services/files_service.py`, `storage.py`, `scanner.py` | Uploads: validate → ClamAV scan (optional) → extract text → store bytes under a random key → chunk/index |
| `services/stt.py` | Speech-to-text through an OpenAI-compatible `/audio/transcriptions` endpoint |
| `services/turns.py` | Runs each reply as a background task that outlives the connection; live subscribers replay its events; notifies when nobody was watching at the end |
| `services/push.py` | Push notifications: FCM HTTP v1 (service-account JWT) and APNs token auth (ES256, HTTP/2); dead device tokens are removed |
| `services/export.py` | Markdown, text and PDF (fpdf2 + bundled DejaVu fonts) conversation exports |
| `services/knowledge_service.py` | Knowledge runtime (search provider, fetcher, embedder), library ingestion, hybrid retrieval (pgvector `<=>` on PostgreSQL), background auto-indexing |
| `api/routes/*` | REST endpoints, SSE streaming, WebSocket endpoint |

### API (prefix `/api/v1`)

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /health/ready` | Liveness; readiness (DB + at least one provider) |
| `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` | Email/password auth with rotating refresh tokens. With two-step verification, login returns `{"mfa_required": true, "mfa_token"}` instead of tokens |
| `POST /auth/mfa/verify` | Second sign-in step: authenticator or recovery code + `mfa_token` → tokens |
| `POST /auth/oauth/{google,apple}` | Sign in or sign up with a provider ID token (`id_token`, optional `nonce`, `display_name`) |
| `POST /users/me/email-verification`, `…/confirm` | Email a 6-digit code; confirm it |
| `POST /users/me/mfa/setup`, `/enable`, `/disable`, `/recovery-codes` | Two-step verification management |
| `GET /users/me/identities`, `DELETE /users/me/identities/{provider}` | Linked Google / Apple accounts |
| `GET/PATCH/DELETE /users/me`, `GET /users/me/export` | Profile, model preferences, account deletion, data export |
| `GET /models` | Models currently configured on the server, plus Dhanz's greeting |
| `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}` | History, search (`?q=`), rename, pin, delete |
| `GET /conversations/{id}/export?format=markdown\|txt` | Export a conversation |
| `GET/POST /knowledge/documents`, `GET/DELETE /knowledge/documents/{id}` | Knowledge library: list/filter, add a public URL, read, delete |
| `GET /knowledge/search?q=` | Hybrid search over the user's library |
| `PATCH /knowledge/documents/{id}` | Move a document into or out of a project |
| `POST /files`, `GET /files/{id}/download` | Upload a document/image (multipart, optional `project_id`); download it back |
| `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` | Project workspaces (name, description, instructions) |
| `GET/POST/DELETE /memories`, `PATCH/DELETE /memories/{id}` | Opt-in memory (toggle with `PATCH /users/me {"memory_enabled": …}`) |
| `POST /voice/transcribe` | Speech-to-text for the voice assistant |
| `POST /conversations/{id}/messages` | Send (or edit-and-resend) and stream the reply as SSE; `web: true\|false\|null` controls research |
| `POST /conversations/{id}/regenerate` | Regenerate the last reply as SSE |
| `POST /conversations/{id}/stop` | Stop the reply being generated (keeps the partial text as `stopped`) |
| `WS /ws/chat` | Same chat protocol over WebSocket (auth frame first) |
| `POST /devices`, `POST /devices/unregister` | Register / remove this phone's push token |
| `GET /app/updates?platform=&version=` | Is a newer app version available (from the release `latest.json`)? No auth needed |
| `GET /auth/options` | Registration open, password reset, email verification (required?), Google client ID, Apple sign-in (no auth) |
| `POST /auth/password-reset/request`, `/auth/password-reset/confirm` | Email a one-time code; set a new password with it |
| `POST /users/me/password` | Change password (other devices are signed out) |
| `GET /users/me/sessions`, `DELETE /users/me/sessions/{id}`, `POST /users/me/sessions/revoke-others` | Signed-in devices |
| `GET /admin/stats`, `GET /admin/users`, `PATCH /admin/users/{id}`, `GET /admin/audit` | Administration (role `admin`) |
| `GET/POST /reminders`, `PATCH/DELETE /reminders/{id}`, `GET /reminders/{id}/calendar.ics` | Reminders and calendar export |
| `GET /metrics` (no prefix) | Prometheus metrics, only with `METRICS_TOKEN` |

`POST /conversations/{id}/messages` also takes `attachment_ids`; conversations take an optional
`project_id`; exports take `format=markdown|txt|pdf`.

Interactive OpenAPI docs are served at `/docs` outside production.

### Streaming protocol

Both SSE and WebSocket emit the same JSON events:

1. `meta` — `conversation_id`, `assistant_message_id`, the saved `user_message`
2. `research` (zero or more) — `stage`: `searching` (`query`), `reading` (`urls`), `done`,
   `sources` (numbered citations), `reading_files` (attachments), `unavailable` (no search provider) or `error`;
   `memory` — something the user asked Dhanz to remember was saved
3. `tool` (zero or more) — `stage: "running"` with `labels` (e.g. "Calculating") while tools run, then
   `stage: "done"` with `activity` ([{tool, summary, error, action}]; `action` is a reminder or an email draft)
4. `model` — `provider`, `model` actually used (emitted again if a fallback happens before output)
5. `delta` — `text` (append-only)
6. `done` — final saved `message` (content, tokens, model, `citations`, `tool_activity`) **or** `error` — `detail` + saved message
   **or** `stopped` — the reply was stopped; saved partial `message`

The assistant row is created as `streaming` before the model is called and finalised as
`complete`, `error` or `stopped`. Partial output is never lost.

**Replies run in the background (Phase 4).** A reply is a server task (`services/turns.py`), not
part of the HTTP request: if the connection drops (phone locked, app switched, network change)
the reply still finishes and is saved. The app then follows it by reloading the conversation while
its last message is `streaming`, and on Android/iOS a push notification ("Dhanz finished your
answer", with no question or answer text) is sent if no client was watching when it finished.
Stopping is explicit: `POST /conversations/{id}/stop` cancels the task when it runs in the same
worker, otherwise marks the row `stopping`, which the worker running it checks every second.
Replies in progress when the server shuts down are saved as `stopped`.

## 4. AI engine (`ai_engine/dhanz_ai`)

* `providers/` — one adapter per vendor, all speaking their native streaming wire format over
  `httpx` (OpenAI Chat Completions SSE, Anthropic Messages SSE, Gemini `streamGenerateContent`
  SSE, Ollama NDJSON). Any OpenAI-compatible endpoint works via `OPENAI_BASE_URL`.
* `orchestrator.py` — chooses a model per message:
  1. model the user picked for this chat, 2. user's default model, 3. automatic routing by task
  type (code / reasoning / general, keyword heuristics) and policy (`balanced`, `best`,
  `cheapest`, `local_first`) using each model's capabilities and cost tier.
  If a provider fails **before** emitting text with a retryable error (429/5xx/network), the next
  candidate is tried. Errors after partial output are surfaced, never silently mixed.
* `prompts.py` — Dhanz's identity and rules: separate facts from estimates, never fabricate
  sources or claim actions that did not happen, treat external content as untrusted data, state
  plainly when there is no web access; with sources, cite them as `[n]` and flag conflicts.

### Tool calling

`Orchestrator.stream_chat(..., tools, run_tool)` offers tools only to models with
`Capability.TOOLS`. Each provider adapter translates `ToolSpec`/`ToolCall`/`ToolResult` to its own
wire format (OpenAI `tool_calls`, Anthropic `tool_use`/`tool_result` blocks, Gemini
`functionCall`/`functionResponse` with thought signatures echoed back, Ollama `tool_calls`). When the
model asks for tools, the orchestrator runs them, appends the results and calls the same model
again, up to 5 rounds, then emits a single `done` chunk with summed token counts. A failing tool
becomes an error result the model can explain. The backend's `ToolBox` validates every argument
(the model is untrusted input) and records what happened for the app.

### Research flow (Phase 2)

```
message ──► web mode / needs_search? ──► search API ──► fetch top pages in parallel
                                              │          (robots.txt, SSRF checks, size/type limits)
pasted links ─────────────────────────────────┘                  │
                                                 extract ─► chunk ─► BM25 rank ─► best passages
user's knowledge library ─► hybrid search (keyword ∪ pgvector, RRF) ─────────────┘
                                                        │
                       numbered <sources> block (+ notes on unreadable pages) ─► system prompt
                                                        │
                        streamed answer citing [n]  +  source cards in the app
                                                        │
                        pages saved to the library in the background (if the user allows)
```

LangGraph is not used in Phases 1–2: single-turn routing does not need a graph runtime. It is the
planned choice for Phase 2/3 multi-step flows (research → read → cite, tool use with approvals).

## 5. Data model

```
users 1──* conversations 1──* messages        users 1──* refresh_tokens (family_id)
users 1──* audit_logs (user_id SET NULL on delete)
```

* `messages.position` is unique per conversation, giving a total order and a cheap guard against
  concurrent writers (a second concurrent turn gets HTTP 409).
* Deleting a user cascades to conversations, messages and tokens (data deletion is real).
* Phase 2 added `knowledge_documents` (page text + metadata, unique per user and URL),
  `knowledge_chunks` (text, `embedding vector`, `embedding_model`), `messages.citations` and
  `users.auto_index_web`. Phase 3 added `projects` (conversations and documents reference them, SET NULL
  on delete), `memories`, `users.memory_enabled`, `messages.attachments`, and file columns on
  `knowledge_documents` (`kind = "file"`, type, size, storage key, scan status, extraction notes).
  File bytes live in `STORAGE_DIR` (a Docker volume), are removed when the document or account is deleted.
  Phase 4 added `devices` (push token, platform, app version; unique token, cascades with the user).
  Phase 5 added `password_reset_tokens`, `users.retention_days`, `conversations.temporary` and an
  index on `messages.created_at` (usage statistics).

**Sessions.** A session is a refresh-token family: every refresh rotates the token inside the
family, and access tokens carry the family ID (`sid`). Each authenticated request checks that the
family still has a live token, so revoking a session ends it at once.

## 6. Flutter app (`apps/dhanz_flutter/lib`)

| Path | Responsibility |
|---|---|
| `core/api/api_client.dart` | REST client, single-flight token refresh on 401, SSE chat streams (one HTTP client per stream); *Stop* is an explicit API call |
| `core/platform/push.dart` | Push bridge (`ai.dhanz/push` method channel → `MainActivity.kt` / `AppDelegate.swift`) and device registration |
| `core/platform/desktop*.dart` | Windows/macOS/Linux tray icon, minimize to tray, desktop notifications |
| `core/platform/updates.dart`, `installer_io.dart` | Update check and banner; Windows installer download with SHA-256 verification |
| `core/storage/secure_store.dart` | Tokens/settings in Keychain / Android Keystore / Windows DPAPI |
| `features/auth` | Auth state (`AsyncNotifier`), sign-in / registration screen with server URL override |
| `features/chat` | Chat state machine (follows replies still generating on the server), Markdown + highlighted code, composer, model picker, drag-and-drop attachments |
| `features/conversations` | History panel: search, rename, pin, export, delete |
| `features/chat/sources_view.dart` | Numbered, clickable source cards with site and dates |
| `features/library` | Knowledge library: add page, list, preview, search, remove |
| `features/projects` | Project switcher (in the history panel), projects screen, move chats/documents |
| `features/memory` | Memory screen: toggle, list, add, edit, delete |
| `features/voice` | Voice screen and controller: recording with level-based end-of-speech detection, transcription, spoken replies, hands-free loop, wake phrase |
| `core/files.dart` | File picking and "save as" (attachments, downloads, exports) |
| `features/settings` | Profile, theme, default model, routing policy, data export, account deletion, sign-out |
| `features/account` | Password & devices screen, change-password dialog, forgot-password flow |
| `features/admin` | Administration screen (statistics, accounts) for administrators |
| `router.dart` | GoRouter with auth-aware redirects |

Layout is responsive: ≥ 900 px wide shows a permanent history panel (desktop/tablet); narrower
screens use a drawer (phones).

## 7. Security model (summary)

See [SECURITY.md](SECURITY.md). In short: Argon2id passwords, 15-minute JWT access tokens,
rotating refresh tokens with reuse detection, per-user data isolation (all queries scoped by
owner, 404 for others' IDs), rate limits, validated inputs with size caps, audit logging, HSTS and
security headers, secrets only in server environment, production config validation.
