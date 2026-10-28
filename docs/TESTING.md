# Testing

## Python (AI engine + backend)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt             # also installs ai_engine in editable mode
(cd ai_engine && pytest -q)                             # provider wire formats, routing, fallback
(cd knowledge_engine && pytest -q)                      # search APIs, robots.txt, SSRF, extraction, ranking, research
(cd backend && pytest -q)                               # API: auth, chat, research turns, library, isolation, migrations
TEST_POSTGRES_URL=postgresql+asyncpg://dhanz:...@localhost:5432/dhanz \
  pytest -q backend/tests/test_postgres.py              # pgvector ingestion + hybrid search (CI runs this)
ruff check backend ai_engine knowledge_engine tests scripts
ruff format --check backend ai_engine knowledge_engine tests scripts
```

Knowledge-engine and backend research tests use `httpx.MockTransport` web sites (articles,
robots.txt rules, paywalls, redirects to internal addresses) and a fake search provider, so
they need no network. Backend tests run the real Alembic migration against a temporary SQLite database and use a
deterministic in-test provider (`EchoProvider` in `backend/tests/conftest.py`) so no API keys or
network are needed. Provider adapters are tested against recorded wire formats with
`httpx.MockTransport` (`ai_engine/tests/test_providers.py`).

## PostgreSQL end-to-end smoke test

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, JWT_SECRET and (optionally) a provider key
docker compose up -d --build
python tests/e2e/smoke_test.py --base-url http://localhost:8000
```

The smoke test registers a throwaway user, refreshes tokens, streams a chat reply (or checks the
"no provider configured" error when no key is set), searches, exports and finally deletes the
account. CI runs the same script against a PostgreSQL + pgvector service container after an
`upgrade → downgrade → upgrade` migration round-trip.

## Flutter

```bash
cd apps/dhanz_flutter
flutter pub get
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
```

`test/fake_backend.dart` implements the API (including SSE streaming) in memory, so widget tests
drive the real app: welcome → registration → greeting → send → streamed reply, session restore
on a phone-sized layout, token refresh and session expiry.

## Manual verification checklist (Phase 1)

1. Start the backend with at least one provider key (or Ollama) and open `/docs`.
2. `flutter run -d windows` (or an Android emulator / iOS simulator).
3. Register → the greeting *"Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"* appears.
4. Send a question → the reply streams; the model name appears under it.
5. Ask for code → a highlighted block with a *Copy* button renders.
6. Press *Stop* mid-reply → partial text is kept and marked *Stopped*.
7. *Regenerate* and *Edit* (pencil on your message) → history is replaced from that point.
8. In the history panel: search, rename, pin, export, delete.
9. Settings: switch light/dark, choose default model and routing policy, export data.
10. Restart the app → still signed in. Sign out → back to the welcome screen.
11. Delete account → signed out; logging in again fails.

## Manual verification checklist (Phase 2)

Requires `SEARCH_PROVIDER` configured.

1. Ask *"Hey Dhanz, search the internet for the latest semiconductor technology"* → status
   lines "Searching the web…", "Reading N pages…", then an answer with `[n]` markers and source
   cards (site, publication date, retrieval date). Tapping a card opens the page.
2. Globe button → *Off*, ask the same → no research; Dhanz says it cannot browse.
3. *"Summarise https://…"* with a public article → a summary citing that page.
4. Paste a link to a site whose robots.txt disallows bots → Dhanz says it could not read it.
5. Knowledge library → *Add page* → listed with site and dates; search finds it; ask a related
   question in a new chat → the answer cites it with the library icon.
6. Settings → turn off *Save researched pages* → new research no longer adds documents.
