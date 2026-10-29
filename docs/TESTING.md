# Testing

## Python (AI engine + backend)

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt             # also installs ai_engine in editable mode
(cd ai_engine && pytest -q)                             # provider wire formats, routing, fallback
(cd knowledge_engine && pytest -q)                      # search APIs, robots.txt, SSRF, extraction, ranking, research
(cd backend && pytest -q)                               # API: auth, chat, research turns, library, isolation, migrations
# The same backend suite on PostgreSQL (fresh schema per test) plus the pgvector tests — CI runs this:
TEST_DATABASE_URL=postgresql+asyncpg://dhanz:...@localhost:5432/dhanz \
TEST_POSTGRES_URL=postgresql+asyncpg://dhanz:...@localhost:5432/dhanz (cd backend && pytest -q)
(cd backend && pytest -q --cov=app --cov-fail-under=80)  # coverage gate used in CI
pip-audit -r backend/requirements.txt                   # known vulnerabilities in dependencies
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

## Manual verification checklist (Phase 3)

1. Paperclip in the composer → attach a PDF/Word/Excel file → ask about it → the answer cites the
   file; tap the source card to download it again.
2. Attach a spreadsheet → ask for totals → numbers match the column statistics.
3. Attach two documents → "compare these" → both are cited.
4. Attach a photo or drawing with a vision model configured → it is described; without one,
   Dhanz explains that no configured model can read images.
5. History panel → project switcher → *Manage projects…* → create a project with instructions →
   new chats and uploads go into it; the instructions are followed; another project's documents
   are not used.
6. Settings → Memory → turn on → say "Remember that I prefer metric units" → notice appears and
   the memory is listed; later answers use it; turn off → no longer used.
7. Microphone button in the chat bar → speak → the transcript appears, Dhanz answers aloud;
   enable *Hands-free* and *Require "Hey Dhanz"* and check both behaviours.
8. Conversation menu → *Save as PDF* → the PDF opens with the conversation, code and sources.

Phase 4 tests: `backend/tests/test_phase4.py` covers replies that keep going after the client
disconnects, Stop (same worker and via the database flag), the "answer ready" push sent only when
nobody was watching, FCM and APNs request signing with generated keys (`httpx.MockTransport`),
removal of dead device tokens, device registration and the update check. The Dart side
(`apps/dhanz_flutter/test/phase4_test.dart`) covers following a reply after the connection drops,
Stop through the API, resuming an opened conversation, push registration/refresh/opt-out/sign-out
with a fake platform bridge, the update banner and the installer checksum check.

The native push code (`MainActivity.kt`, `DhanzMessagingService.kt`, `AppDelegate.swift`) and the
desktop tray/notification calls are not covered by automated tests; use the checklist below.

## Manual verification checklist (Phase 4)

1. Windows: Settings → *Keep running in the system tray* → close the window → the tray icon stays;
   left-click restores the window; right-click → *Quit DHANZ AI* exits.
2. Ask a long question, then minimise or hide the window → a desktop notification appears when the
   answer is done; clicking it opens that conversation.
3. Drag a PDF from Explorer onto the chat → it is attached like the paperclip would.
4. Phone: ask a long question, lock the screen → a notification "Dhanz finished your answer"
   arrives (with Firebase/APNs configured); tapping it opens the full answer.
5. Turn on airplane mode mid-answer, then off → the answer still appears complete.
6. Press *Stop* mid-answer → the partial text is kept as *Stopped* (also from a second device).
7. Settings → notifications off → no more notifications; sign out → the device is unregistered.
8. Put a `latest.json` with a higher version on the server → the update banner appears; on Windows
   *Update* downloads, verifies and installs, then the new version starts.

## Load testing

```bash
python tests/load/load_test.py --base-url http://localhost:8000 --users 20 --rounds 10 [--chat]
```

Measured on the 4-core build machine (API in production mode, 2 workers, PostgreSQL 16 and
Redis in containers on the same machine, no AI provider configured so `--chat` measures the
reply pipeline up to the "no provider" result, not model latency):

| Operation | p50 | p95 |
|---|---|---|
| list conversations | 45 ms | 99 ms |
| create conversation | 49 ms | 88 ms |
| open conversation | 36 ms | 79 ms |
| chat request to final event | 139 ms | 320 ms |
| register (Argon2, 20 at once) | 1.3 s | 1.5 s |

≈150 requests/s overall with 20 concurrent users and no errors. Real chat latency is dominated
by the AI provider. Argon2 is deliberately slow and CPU-bound; it runs in worker threads so it
does not hold up other requests. Raise the auth/chat rate limits on a test server, or you
measure the limiter.

## Manual verification checklist (Phase 5)

1. Sign in on two devices → Settings → *Password & devices* lists both; *Sign out* the other →
   it is signed out on its next action (not after 15 minutes).
2. *Change password* → other devices are signed out; the new password works.
3. With SMTP configured: login screen → *Forgot your password?* → code arrives by email → new
   password works; a wrong code five times makes the code useless.
4. Wrong password 5 times → the account is locked for 15 minutes (other accounts unaffected).
5. Settings → *Delete old conversations* → 30 days; `python -m app.cli maintenance` removes
   older ones. Timer icon in a new chat → temporary chat banner; "Remember that …" is not saved.
6. First account → Settings → *Administration* shows statistics and accounts; deactivate a test
   account → it is signed out immediately.
7. `curl -H "Authorization: Bearer $METRICS_TOKEN" https://<server>/metrics` shows `dhanz_*` metrics;
   every response has an `X-Request-ID` that appears in the JSON logs.
