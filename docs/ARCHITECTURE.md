# DHANZ AI — System Architecture

> Your World. Your Knowledge. Your AI.

This document describes the target architecture for all phases and marks what exists today
(**Phase 1**) versus what is planned. See [ROADMAP.md](ROADMAP.md) for the phase plan and the
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
│                    │ AI engine (/ai_engine)      │      │ Knowledge engine (Phase 2)    │ │
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
| `knowledge_engine` | Web research + RAG (search, fetch, chunk, embed, retrieve) | Phase 2 (not started) |
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
| `services/chat_service.py` | Turn preparation (send / edit-and-resend / regenerate), history building, streaming + persistence |
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
| `POST /conversations/{id}/messages` | Send (or edit-and-resend) and stream the reply as SSE |
| `POST /conversations/{id}/regenerate` | Regenerate the last reply as SSE |
| `WS /ws/chat` | Same chat protocol over WebSocket (auth frame first) |

Interactive OpenAPI docs are served at `/docs` outside production.

### Streaming protocol

Both SSE and WebSocket emit the same JSON events:

1. `meta` — `conversation_id`, `assistant_message_id`, the saved `user_message`
2. `model` — `provider`, `model` actually used (emitted again if a fallback happens before output)
3. `delta` — `text` (append-only)
4. `done` — final saved `message` (content, tokens, model) **or** `error` — `detail` + saved message

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
  plainly that there is no live web access (until Phase 2 adds it).

LangGraph is not used in Phase 1: single-turn routing does not need a graph runtime. It is the
planned choice for Phase 2/3 multi-step flows (research → read → cite, tool use with approvals).

## 5. Data model

```
users 1──* conversations 1──* messages        users 1──* refresh_tokens (family_id)
users 1──* audit_logs (user_id SET NULL on delete)
```

* `messages.position` is unique per conversation, giving a total order and a cheap guard against
  concurrent writers (a second concurrent turn gets HTTP 409).
* Deleting a user cascades to conversations, messages and tokens (data deletion is real).
* Phase 2 adds `documents`, `chunks (embedding vector)`, `sources`; Phase 3 adds `memories`,
  `projects`, `files`.

## 6. Flutter app (`apps/dhanz_flutter/lib`)

| Path | Responsibility |
|---|---|
| `core/api/api_client.dart` | REST client, single-flight token refresh on 401, SSE chat streams (one HTTP client per stream so *Stop* aborts the request) |
| `core/storage/secure_store.dart` | Tokens/settings in Keychain / Android Keystore / Windows DPAPI |
| `features/auth` | Auth state (`AsyncNotifier`), sign-in / registration screen with server URL override |
| `features/chat` | Chat state machine, Markdown + highlighted code, composer, model picker |
| `features/conversations` | History panel: search, rename, pin, export, delete |
| `features/settings` | Profile, theme, default model, routing policy, data export, account deletion, sign-out |
| `router.dart` | GoRouter with auth-aware redirects |

Layout is responsive: ≥ 900 px wide shows a permanent history panel (desktop/tablet); narrower
screens use a drawer (phones).

## 7. Security model (summary)

See [SECURITY.md](SECURITY.md). In short: Argon2id passwords, 15-minute JWT access tokens,
rotating refresh tokens with reuse detection, per-user data isolation (all queries scoped by
owner, 404 for others' IDs), rate limits, validated inputs with size caps, audit logging, HSTS and
security headers, secrets only in server environment, production config validation.
