# DHANZ AI

**Your World. Your Knowledge. Your AI.**

DHANZ AI is a cross-platform AI assistant — *Dhanz* — for Windows 10/11, Android and
iPhone/iPad, built with Flutter on top of a FastAPI backend that routes each message to OpenAI,
Anthropic Claude, Google Gemini or a local Ollama model.

> "Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"

| Desktop | Phone |
|---|---|
| ![Chat on desktop](docs/screenshots/chat-desktop.png) | ![Chat on a phone](docs/screenshots/chat-phone.png) |

## Status

**Phase 1 — working MVP:** accounts, multi-provider AI with automatic model routing and
fallback, streaming chat, conversation history (search, rename, pin, export, delete),
regenerate / edit-and-resend / stop, Markdown with code highlighting, light & dark themes,
privacy controls (data export, account deletion), CI and release pipelines.

**Phase 2 — internet intelligence:** live web search (Brave, Tavily or SearXNG), polite page
reading that respects robots.txt and never bypasses paywalls, webpage summarisation, answers
with numbered clickable citations and publication/retrieval dates, and a private knowledge
library with hybrid keyword + semantic (pgvector) retrieval.

| Web research with sources | Answer from your knowledge library |
|---|---|
| ![Research answer with sources](docs/screenshots/research-sources.png) | ![Answer citing the library](docs/screenshots/library-answer.png) |

Voice, document analysis, memory and projects are **not implemented yet** — see
[docs/ROADMAP.md](docs/ROADMAP.md) for the exact status of every feature.

## Quick start

```bash
# 1. Backend (Docker)
cp .env.example .env          # set POSTGRES_PASSWORD, JWT_SECRET, one AI provider key and
                              # (optional) SEARCH_PROVIDER + key for web research
docker compose up -d --build
curl http://localhost:8000/api/v1/health/ready

# 2. App
cd apps/dhanz_flutter
flutter pub get
flutter run -d windows        # or an Android emulator / iOS simulator
```

Full instructions for every platform, including installers, APK/AAB and signed iOS builds:
[docs/INSTALL.md](docs/INSTALL.md).

## Repository layout

```
apps/dhanz_flutter   Flutter app (Windows, Android, iOS; macOS/web scaffolding)
backend              FastAPI API, SQLAlchemy models, Alembic migrations, tests
ai_engine            dhanz_ai package: OpenAI / Anthropic / Gemini / Ollama adapters + orchestrator
knowledge_engine     dhanz_knowledge: search APIs, safe fetching, extraction, embeddings, ranking
database             PostgreSQL init (pgvector, pg_trgm)
tests/e2e            Smoke test against a running API
scripts              App icon generator, Windows installer (Inno Setup)
.github/workflows    CI and release builds
docs                 Architecture, install, testing, security, release, roadmap
```

## Documentation

* [Architecture](docs/ARCHITECTURE.md) — components, API, streaming protocol, data model
* [Installation](docs/INSTALL.md) — backend, Windows, Android, iOS, macOS
* [Testing](docs/TESTING.md) — unit, widget, end-to-end, manual checklist
* [Security & privacy](docs/SECURITY.md) — controls in place and known limitations
* [Release](docs/RELEASE.md) — signing, CI secrets, release checklist
* [Roadmap](docs/ROADMAP.md) — phases and implementation status

## Tech stack

Flutter · Dart · Riverpod · GoRouter · Python 3.11+ · FastAPI · SQLAlchemy 2 (async) · Alembic ·
PostgreSQL 16 + pgvector · BeautifulSoup/lxml · Redis (reserved for job queues) · Docker · GitHub Actions.

---

The archives `VideoToMP3.zip` and `VideoToMP3Android.zip` predate DHANZ AI and are kept unchanged.
