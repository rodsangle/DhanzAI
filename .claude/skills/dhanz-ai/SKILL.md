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

## Current state (2026-11-03)

- `main` = **0.8.0** (`apps/dhanz_flutter/pubspec.yaml` `0.8.0+8`, API version in
  `backend/app/main.py`). CI and CodeQL green. Includes public accounts (email codes, TOTP two-step,
  Google/Apple sign-in), Office file generation + previews, Creative Studio (images via
  OpenAI-compatible or xAI key with fail-closed screening, Runway video, credits ledger), optional
  PDF OCR (Poppler + Tesseract), JWKS fresh-boot fix.
- Alembic heads on `main`: `0007_creative_studio_jobs_credits_and_`, `0008_public_accounts`.
- Releases on GitHub: `v0.8.0` (from main), `v0.8.1` (Tailscale), `v0.8.2` (downloads + daily local
  news), `desktop-0.7.0`, `desktop-0.9.0` (Windows installer). README still links the 0.7.0 installer.
- **Diverged release branch:** `v0.8.1`, `v0.8.2` and `desktop-0.9.0` were built from
  `codex/tailscale-build-0.8.2`, which forked from main *before* 0.8.0 (merge-base `f00049b`) and was
  never merged. It adds: per-account read-only GitHub repository assistance (`github_service.py`,
  `routes/github.py`, `docs/GITHUB.md`), private Tailscale server config (`docs/TAILSCALE.md`,
  `tailscale-build.yml`), visible document Download controls, a daily local news button. So those
  installers **lack** 0.8.0's public accounts and Office files, and main lacks the Tailscale/GitHub
  features. Merging it into main conflicts in `auth_controller.dart`, `chat_screen.dart`,
  `tool_activity_view.dart`, `pubspec.yaml`, `assistant_tools.py`, `chat_service.py`,
  `scripts/windows/dhanz_ai.iss`, and its migration `0008_github_connections.py` collides with
  `0008_public_accounts.py` (renumber to `0009`, `down_revision` = public accounts).
- **Open PR #37** "Add Coding Agent mode" (`feature/coding-agent-mode`, 7 commits, up to date with
  main): backend + Flutter green except `dart format` (one file unformatted) — fix with
  `dart format lib test` in `apps/dhanz_flutter`.

## Open work (in priority order)

1. Merge `codex/tailscale-build-0.8.2` into `main` (resolve the conflicts above, renumber the
   migration), then bump to 0.9.x so version numbers match the published installers.
2. Fix formatting on PR #37 and merge it.
3. Public-platform Milestone B: Free/Plus/Pro plans in the database, usage metering and quotas, AI
   cost tracking, Stripe Checkout + signed webhooks, Google Play Billing and StoreKit 2 verified
   server-side. (Creative Studio already has a credit ledger and plan allowances to build on.)
4. Milestone C: web admin dashboard (plans/quotas/providers config, abuse reports, announcements,
   metrics). Milestone D: web hosting, content moderation for chat, privacy policy/terms, store
   listings, object storage for uploads, bot protection on sign-up.
5. Google sign-in on web/desktop and Apple sign-in off iOS; device testing of push, tray, updates.

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
