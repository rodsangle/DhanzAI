---
name: dhanz-ai
description: Project memory and working guide for DHANZ AI (this repository). Use whenever continuing, updating, fixing, releasing or planning DHANZ AI — it holds the current progress, open work, repo layout, the checks CI runs, release steps and known pitfalls. Update its "Current state" and "Progress log" sections at the end of every session that changes the project.
---

# DHANZ AI — project skill

DHANZ AI is a cross-platform AI assistant ("Dhanz", tagline *Your World. Your Knowledge. Your AI.*):
Flutter apps (Windows, Android, iOS, web, macOS) on a Python FastAPI backend that routes chats to
OpenAI, Anthropic, Gemini, xAI (Creative Studio images) and local Ollama models. Owner: GitHub
`rodsangle`, repository `rodsangle/DhanzAI` (formerly `videotomp3`; GitHub tools may need the repo
name `dhanzai`).

## How to use this skill

1. Read **Current state** and **Open work** below before changing anything.
2. Sync first: `git fetch origin --tags` and compare `main` with any release branch listed below —
   other agents (Cursor, Codex, Dependabot) also push to this repo, so this file can lag behind.
3. Make the change, run the **Checks** for what you touched, commit, push to your session branch.
4. Before finishing, update **Current state**, **Open work** and add one line to **Progress log**
   (date, what changed, where it lives). Keep entries short and factual; never claim a feature works
   unless it was tested.

## Project rules (from the owner's specifications)

- No fabricated sources, no mock features presented as complete: a screen is only shown when the
  feature works. Mark partial work 🟡 in `docs/ROADMAP.md` with the reason.
- AI provider keys and payment/signing secrets live only on the backend or in GitHub secrets.
- Web research respects robots.txt and never bypasses paywalls or logins.
- Users' private chats are not readable by administrators.
- Ship in milestones: implement → test → push; keep `CHANGELOG.md`, `docs/ROADMAP.md` and the
  version numbers in step.
- Git: work on the session's assigned branch; no PRs unless the owner asks; never rewrite others'
  history (merge, don't rebase/force-push shared branches); no model names in commits or code.

## Current state (2026-11-12)

- **Live site:** dhanzai.com on a custom AWS server (Docker Compose behind Caddy). Its API is the
  repository backend plus changes applied by `deploy/updaters/*.py` (code embedded as base64/gzip
  payloads, pinned to fingerprints of the running server). Its web app is built from
  `apps/dhanz_flutter` by `.github/workflows/web-updates.yml` (manual dispatch only; it publishes
  `web-updates-*` prereleases and moves the `web-update-channel` the server installs from).
  Bump `pubspec.yaml` and the workflow's `WEB_VERSION`/`WEB_BUILD`/`RELEASE_ID` together.
- **One Flutter app:** `apps/dhanz_flutter` = the live client (0.10.12+53) + native projects. It has
  the three themes (`lib/core/theme.dart`), public-account screens (two-step shown only when the
  user JSON contains `mfa_enabled`), and the old app's tests on `test/fake_backend.dart`.
- Not ported from the old app: its creative-activity indicator ("N creations in progress").
- Models: `scripts/server/upgrade_models.py` (run on AWS) switches to the newest chat/image models the
  server's keys answer with. ROG (Ryzen AI Max+ 395, 128 GB, 64 GB to GPU, Ubuntu 24.04 WSL2):
  `setup_next_models.py` tests Wan 2.2 TI2V-5B and Z-Image-Turbo; not yet wired to the worker.
- CI fails properly now: the Flutter job runs bash with pipefail (it used to hide failing analyze/test
  behind `| tee`).
- Updater fingerprints use `ast.dump`, whose output differs between Python versions: run
  `tests/test_attachment_updater.py` with Python 3.12 (CI and the server), not 3.13.
- Still unmerged elsewhere: `codex/tailscale-build-0.8.2` (Tailscale server, GitHub access), PR #37
  (Coding Agent mode), Dependabot PRs #39–#46.

## Open work (in priority order)

1. Retire the updater scripts: move their payload code into `backend/` as readable source with
   Alembic migrations, build the image in CI, deploy by image tag with a rollback tag.
2. Merge `codex/tailscale-build-0.8.2` (renumber its `0008` migration) and PR #37; clear Dependabot.
3. One version number across the app, API, web releases and installers; README installer link.
4. Public-platform Milestone B: Free/Plus/Pro plans in the database, usage metering and quotas, AI
   cost tracking, Stripe Checkout + signed webhooks, Google Play Billing and StoreKit 2 verified
   server-side. (Creative Studio already has a credit ledger and plan allowances to build on.)
5. Milestone C: web admin dashboard (plans/quotas/providers config, abuse reports, announcements,
   metrics). Milestone D: web hosting, content moderation for chat, privacy policy/terms, store
   listings, object storage for uploads, bot protection on sign-up.
6. Google sign-in on web/desktop and Apple sign-in off iOS; device testing of push, tray, updates.

Full feature status: `docs/ROADMAP.md`. Spec text: `docs/PROJECT_REQUIREMENTS.md`.

## Repository map

| Path | What |
|---|---|
| `backend/app/main.py` | FastAPI app factory, routers, lifespan, content-route email gate |
| `backend/app/api/routes/` | auth, users, conversations, knowledge, files, projects, memories, voice, reminders, creative, devices, updates, realtime, admin, meta |
| `backend/app/services/` | chat_service (turns), accounts + oauth (sign-in), assistant_tools, office_files, file_preview, knowledge_service, reminders, push, maintenance, mailer, storage, scanner, stt |
| `backend/app/core/` | config (all env settings), security, mfa, rate_limit, observability |
| `backend/alembic/versions/` | migrations — keep one head; new files get the next number |
| `ai_engine/dhanz_ai/` | provider adapters + orchestrator (routing, fallback, tool loop) |
| `knowledge_engine/dhanz_knowledge/` | search providers, fetcher (robots/SSRF rules), chunking, embeddings |
| `apps/dhanz_flutter/lib/` | `core/` (api client, providers, platform bridges), `features/*` screens, `router.dart`, `models/models.dart` |
| `apps/dhanz_flutter/test/fake_backend.dart` | in-memory API used by widget tests — extend it with new endpoints |
| `.github/workflows/` | `ci.yml`, `codeql.yml`, `release.yml` (tags `v*` publish a release), `windows-installer.yml` |
| `deploy/` | production compose, Caddy (HTTPS), Creative Studio worker |
| `docs/` | INSTALL, DEPLOY, RELEASE, SECURITY, TESTING, ARCHITECTURE, ROADMAP, CREATIVE_STUDIO, OCR, … |

## Checks (what CI runs — run the relevant ones before pushing)

```bash
# Python (from repo root; a venv with backend/requirements-dev.txt installed)
ruff check backend ai_engine knowledge_engine tests scripts
ruff format --check backend ai_engine knowledge_engine tests scripts
(cd ai_engine && pytest -q --cov=dhanz_ai --cov-fail-under=85)
(cd knowledge_engine && pytest -q --cov=dhanz_knowledge --cov-fail-under=85)
(cd backend && pytest -q --cov=app --cov-fail-under=80)
# PostgreSQL run: start Postgres+pgvector, then
#   TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db pytest -q
# and: alembic upgrade head && alembic downgrade base && alembic upgrade head && alembic check

# Flutter (apps/dhanz_flutter)
flutter pub get
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build web --release
```

Native Android/iOS/macOS/Windows builds only happen on GitHub runners: run the *Release builds*
workflow manually (workflow_dispatch) on the branch to verify plugins compile.

## Releasing

- Bump `pubspec.yaml` (`x.y.z+build`), the API version in `backend/app/main.py`, and `CHANGELOG.md`.
- Push a tag `vX.Y.Z` → `release.yml` builds all platforms and publishes the GitHub Release with
  `latest.json` (in-app update manifest). Agent sessions usually cannot push tags (403): ask the owner
  to create the release/tag on GitHub.
- Signing secrets and variables are listed in `docs/RELEASE.md` (Android keystore, iOS cert/profile,
  Windows PFX, `DHANZ_API_URL`, `GOOGLE_IOS_CLIENT_ID`, Firebase JSON).

## Pitfalls learned

- `scripts/release/package_web_updates.py` reads WEB_VERSION/WEB_BUILD/RELEASE_ID from the workflow;
  it once hard-coded 0.10.11+52 and failed the 0.10.12 publish. Run it locally before a release.
- OpenAI GPT-5.5/5.6/6.x reject function tools on /v1/chat/completions unless reasoning_effort is
  'none', and accept only temperature 1. The live server (2026-11-13) runs gpt-5.4, gpt-5.4-mini,
  gpt-4.1-mini, gpt-4.1 at temperature 0.7 and gpt-image-2.6-sunburst. A 400 from a provider is not
  is now retried on the next model (AI engine update), and the OpenAI adapter adapts those settings.
  Install AI engine changes on the server with `scripts/server/deploy_ai_engine.py` (rollback image).
- `tray_manager` must stay on 0.5.x (0.6+ needs native libraries that break `flutter test`);
  Dependabot ignores `>=0.6.0`.
- Pin third-party GitHub Actions to commit SHAs (CodeQL flags tags).
- Avoid regexes with nested/overlapping quantifiers on user text (CodeQL ReDoS); bound input length.
- Tests that read settings must not depend on CI env vars (`monkeypatch.delenv`, `_env_file=None`).
- Two migrations with the same number from parallel branches create two Alembic heads — renumber
  when merging.
- When a Dependabot PR conflicts after others merge, Dependabot rebases it itself within minutes; an
  `@dependabot rebase` comment only works if the owner posts it.
- macOS product is `DHANZ AI.app` (PRODUCT_NAME), not `dhanz_ai.app`.
- In cloud sessions: Flutter is at `/opt/flutter` (runs as root with a warning); Docker must be
  started with `dockerd` before Postgres tests.

## Progress log

- 2026-10-29 — Phases 1–5 and assistant tools complete; CodeQL fixes; Dependabot PRs #2–#19 handled;
  release workflow fixes (macOS bundle name, branch artifact names).
- 2026-10-29 — Public accounts milestone (email verification, TOTP two-step, Google/Apple sign-in),
  merged to main via PR #30.
- 2026-10-30/31 — (other agents) Creative Studio, OCR, Office documents, xAI images, 0.8.0; Tailscale
  and GitHub-assist releases 0.8.1/0.8.2/desktop-0.9.0 on an unmerged branch.
- 2026-11-02 — (owner) PR #37 Coding Agent mode opened.
- 2026-11-03 — Reviewed repo state; created this skill.
- 2026-11-03 — Three selectable themes + Follow system, preference migration, contrast tests
  (merged to main in PR #38).
- 2026-11-03/11 — (Codex) web releases 0.9.3–0.10.11 and server updaters on `codex/*` branches.
- 2026-11-12 — Consolidation PR: production branch merged into main, duplicate theme picker dropped
  (its `theme_style` choice migrates), seven old client snapshots removed, CI pipefail and lint fixed.
- 2026-11-12 — One Flutter app: live client moved to `apps/dhanz_flutter` with themes and account
  screens (web 0.10.12+53); web-updates workflow made manual.
- 2026-11-13 — Server model-upgrade script; ROG test stage for Wan 2.2 TI2V-5B + Z-Image-Turbo.
- 2026-11-13 — Web publish fix: packager takes its version from the workflow (0.10.12 run failed on it).
- 2026-11-13 — Live: web 0.10.12 installed; chat on gpt-5.4 family, images gpt-image-2.6-sunburst (GPT-6 needs a backend change).
- 2026-11-13 — GPT-6 support: adaptive OpenAI settings, fallback on refused requests, deploy_ai_engine.py (rehearsed).
- 2026-11-13 — ChatGPT parity round 1 (replica/): branch, archive, share links; app/conversation_extras + deploy_conversation_extras.py (rehearsed); web 0.10.14.
