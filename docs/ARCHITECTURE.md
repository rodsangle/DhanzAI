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
| `core/rate_limit.py` | Sliding-window limiter for auth (per IP) and chat (per user) |
| `models/` | `users`, `refresh_tokens`, `conversations`, `messages`, `audit_logs` |
| `services/auth_service.py` | Token issue, rotation, reuse detection (revokes the whole session family) |
| `services/chat_service.py` | Turn preparation (send / edit-and-resend / regenerate), research phase, history building, streaming + persistence |
| `services/files_service.py`, `storage.py`, `scanner.py` | Uploads: validate → ClamAV scan (optional) → extract text → store bytes under a random key → chunk/index |
| `services/stt.py` | Speech-to-text through an OpenAI-compatible `/audio/transcriptions` endpoint |
| `services/export.py` | Markdown, text and PDF (fpdf2 + bundled DejaVu fonts) conversation exports |
| `services/knowledge_service.py` | Knowledge runtime (search provider, fetcher, embedder), library ingestion, hybrid retrieval (pgvector `<=>` on PostgreSQL), background auto-indexing |
| `api/routes/*` | REST endpoints, SSE streaming, WebSocket endpoint |

### API (prefix `/api/v1`)

| Method & path | Purpose |
|---|---|
| `GET /health`, `GET /health/ready` | Liveness; readiness (DB + at least one provider) |
| `POST /auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` | Email/password auth with rotating refresh tokens |
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
| `WS /ws/chat` | Same chat protocol over WebSocket (auth frame first) |

`POST /conversations/{id}/messages` also takes `attachment_ids`; conversations take an optional
`project_id`; exports take `format=markdown|txt|pdf`.

Interactive OpenAPI docs are served at `/docs` outside production.

### Streaming protocol

Both SSE and WebSocket emit the same JSON events:

1. `meta` — `conversation_id`, `assistant_message_id`, the saved `user_message`
2. `research` (zero or more) — `stage`: `searching` (`query`), `reading` (`urls`), `done`,
   `sources` (numbered citations), `reading_files` (attachments), `unavailable` (no search provider) or `error`;
   `memory` — something the user asked Dhanz to remember was saved
3. `model` — `provider`, `model` actually used (emitted again if a fallback happens before output)
4. `delta` — `text` (append-only)
5. `done` — final saved `message` (content, tokens, model, `citations`) **or** `error` — `detail` + saved message

The assistant row is created as `streaming` before the model is called and finalised as
`complete`, `error` or `stopped` (client disconnected). Partial output is never lost.

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

## 6. Flutter app (`apps/dhanz_flutter/lib`)

| Path | Responsibility |
|---|---|
| `core/api/api_client.dart` | REST client, single-flight token refresh on 401, SSE chat streams (one HTTP client per stream so *Stop* aborts the request) |
| `core/storage/secure_store.dart` | Tokens/settings in Keychain / Android Keystore / Windows DPAPI |
| `features/auth` | Auth state (`AsyncNotifier`), sign-in / registration screen with server URL override |
| `features/chat` | Chat state machine, Markdown + highlighted code, composer, model picker |
| `features/conversations` | History panel: search, rename, pin, export, delete |
| `features/chat/sources_view.dart` | Numbered, clickable source cards with site and dates |
| `features/library` | Knowledge library: add page, list, preview, search, remove |
| `features/projects` | Project switcher (in the history panel), projects screen, move chats/documents |
| `features/memory` | Memory screen: toggle, list, add, edit, delete |
| `features/voice` | Voice screen and controller: recording with level-based end-of-speech detection, transcription, spoken replies, hands-free loop, wake phrase |
| `core/files.dart` | File picking and "save as" (attachments, downloads, exports) |
| `features/settings` | Profile, theme, default model, routing policy, data export, account deletion, sign-out |
| `router.dart` | GoRouter with auth-aware redirects |

Layout is responsive: ≥ 900 px wide shows a permanent history panel (desktop/tablet); narrower
screens use a drawer (phones).

## 7. Security model (summary)

See [SECURITY.md](SECURITY.md). In short: Argon2id passwords, 15-minute JWT access tokens,
rotating refresh tokens with reuse detection, per-user data isolation (all queries scoped by
owner, 404 for others' IDs), rate limits, validated inputs with size caps, audit logging, HSTS and
security headers, secrets only in server environment, production config validation.
