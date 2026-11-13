# Deploying and operating the server

This guide puts the DHANZ AI backend on a Linux server with a domain name, HTTPS, PostgreSQL,
Redis, nightly backups and monitoring. The apps then use `https://<your domain>` as their server.

## 1. Requirements

* A Linux server (2 vCPU / 4 GB RAM is enough for a family or small team) with Docker and the
  Docker Compose plugin.
* A domain name whose DNS `A`/`AAAA` record points at the server, and ports 80 and 443 open.
* At least one AI provider key (or an Ollama server).

## 2. Configure

```bash
git clone https://github.com/rodsangle/DhanzAI.git && cd DhanzAI/deploy
cp ../.env.example .env
```

Edit `.env`. At minimum:

| Variable | Value |
|---|---|
| `DHANZ_DOMAIN` | e.g. `dhanz.example.com` |
| `ACME_EMAIL` | your email (Let's Encrypt expiry notices) |
| `POSTGRES_PASSWORD` | a long random password |
| `JWT_SECRET` | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `OLLAMA_BASE_URL` | at least one |
| `ALLOW_REGISTRATION` | `false` for a private server (the first account still can register) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | enables "Forgot password" |
| `METRICS_TOKEN` | a random string if you want Prometheus metrics |

`APP_ENV=production`, `DATABASE_URL`, `REDIS_URL`, `LOG_FORMAT=json` and the storage path are
set by `docker-compose.prod.yml`.

## 3. Start

### Build the browser app first

The same HTTPS domain serves the browser app and `/api/v1` backend. On Windows,
users open that domain in Edge or Chrome; no Windows installation is needed.
The browser defaults to its own origin, so it never calls the user's localhost.
An explicit `DHANZ_API_URL` build setting still overrides this default.

With the Flutter version pinned in `.github/workflows/ci.yml`, run from the
repository root:

```bash
cd apps/dhanz_flutter
flutter pub get
flutter build web --release --no-web-resources-cdn
cd ../../deploy
```

Alternatively, download the `dhanz-web` artifact from a successful CI run and
extract its contents into `apps/dhanz_flutter/build/web` on the server. Ensure
`index.html` is directly inside that directory. Caddy mounts only this public
build output; never copy `.env` files or provider keys into it.

### Start the services

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f api      # migrations run automatically
curl https://dhanz.example.com/api/v1/health/ready          # {"status":"ok", ...}
```

Open `https://dhanz.example.com` in Edge or Chrome. Check sign-up/login, send a
message, and reload a chat URL. Verify that API requests go to this public domain.
The readiness endpoint returns HTTP 503 until a model provider is configured,
even if the database is healthy. Run the existing API smoke test from the
repository root with the Python development dependencies installed:

```bash
python tests/e2e/smoke_test.py --base-url https://dhanz.example.com
```

The smoke test needs registration enabled and creates/deletes a test account.
Create your administrator account before exposing registration publicly.

### Connect the Android app

In the Android app's sign-in screen, expand the server setting and enter
`https://dhanz.example.com` (without `/api/v1`). Alternatively, build an APK
with your domain as its default, from `apps/dhanz_flutter`:

```bash
flutter build apk --release --dart-define=DHANZ_API_URL=https://dhanz.example.com
```

Use your own Android release signing configuration before distribution. The
OpenAI key belongs only in the server's `deploy/.env`, never in an APK or web
build. Android and browser users share the same accounts and conversation data.
Google/Apple sign-in on the web is not wired up; use email/password there.

Register in the app with your server URL. **The first account becomes the administrator**
(Settings → Administration). More administrators: Administration → account menu → *Make
administrator*, or on the server:

```bash
docker compose -f docker-compose.prod.yml exec api python -m app.cli promote someone@example.com
```

The compose file uses the image the release workflow publishes
(`ghcr.io/<owner>/<repo>/api`, lower-case). Pin a version with `DHANZ_IMAGE=ghcr.io/rodsangle/dhanzai/api:0.5.0`
in `.env`. If the package is private, `docker login ghcr.io` first (a GitHub token with
`read:packages`), or make the package public in GitHub → Packages.

## 4. Update

```bash
docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d
```

Database migrations run when the API container starts. Take a backup first (below).

## 5. Backups and restore

The `backup` service writes `deploy/backups/dhanz-YYYYMMDD-HHMM.dump` every 24 hours and keeps
14 days. **Copy them off the server** (e.g. `rclone`, your provider's snapshots). Uploaded files
live in the `uploads` volume: back it up too (`docker run --rm -v deploy_uploads:/d -v $PWD:/b alpine tar czf /b/uploads.tgz -C /d .`).

Restore into an empty database:

```bash
docker compose -f docker-compose.prod.yml stop api
docker compose -f docker-compose.prod.yml exec -T db pg_restore -U dhanz -d dhanz --clean --if-exists < backups/dhanz-20261029-0300.dump
docker compose -f docker-compose.prod.yml start api
```

Test a restore on a spare machine before you need it.

## 6. Monitoring

* **Health**: `GET /api/v1/health` (process up) and `/api/v1/health/ready` (database reachable
  and at least one AI provider configured, otherwise HTTP 503). Point your uptime monitor at `ready`.
* **Logs**: one JSON object per line with `request_id`, `method`, `path`, `status`,
  `duration_ms` and `user_id`. Every response carries the same ID in `X-Request-ID`; ask users
  for it when they report a problem.
* **Metrics**: with `METRICS_TOKEN` set, Prometheus can scrape `https://<domain>/metrics`
  using that bearer token:

  ```yaml
  scrape_configs:
    - job_name: dhanz
      scheme: https
      authorization: { credentials: "<METRICS_TOKEN>" }
      static_configs: [{ targets: ["dhanz.example.com"] }]
  ```

  | Metric | Meaning |
  |---|---|
  | `dhanz_http_requests_total{method,route,status}` | Requests (route is the path template) |
  | `dhanz_http_request_duration_seconds` | Time to response headers |
  | `dhanz_chat_replies_total{outcome}` | Replies by outcome: `done`, `error`, `stopped` |
  | `dhanz_llm_tokens_total{provider,direction}` | Tokens used (cost tracking) |
  | `dhanz_active_replies` | Replies being generated now |
  | `dhanz_push_notifications_total{platform,result}` | Push attempts |
  | `dhanz_maintenance_deleted_total{kind}` | Rows removed by the retention job |

  Useful alerts: `rate(dhanz_chat_replies_total{outcome="error"}[10m]) / rate(dhanz_chat_replies_total[10m]) > 0.2`
  (provider problems), 5xx rate, and `/health/ready` failing.

## 7. Scaling

* Raise `WEB_CONCURRENCY` (worker processes per container; ~1 per CPU core).
* Several API containers behind the proxy work as well: rate limits and login lockout are
  shared through Redis, *Stop* reaches a reply running in any worker through the database, and
  metrics are summed per container (scrape each one).
* Replies in progress are bound to the process generating them; restarting a container stops
  them (they are saved as "stopped").

## 8. Clean-up and retention

The API runs a maintenance job every `MAINTENANCE_INTERVAL_MINUTES` (default 60): it deletes
conversations past each user's retention choice, temporary chats older than
`TEMPORARY_CHAT_HOURS`, expired sessions and reset codes, and audit entries older than
`AUDIT_LOG_RETENTION_DAYS` (default 365). Run it once by hand with
`docker compose -f docker-compose.prod.yml exec api python -m app.cli maintenance`.

## Switching to the newest AI models

`scripts/server/upgrade_models.py` checks every provider that has a key in `deploy/.env`
(OpenAI, Anthropic, Gemini, and the Creative Studio image provider). For chat, it sends each
candidate model one short test request, built like the app's own, and picks only models that
answer. The models you already have stay listed after the new ones as fallbacks. For images, it
picks the newest model the provider's model list shows for your key; no image is generated.
Keys are never printed.

```bash
cd ~/DhanzAI && git pull
sudo python3 scripts/server/upgrade_models.py                    # report only
sudo python3 scripts/server/upgrade_models.py --apply --restart  # save and restart the API
```

`--apply` saves a timestamped `.env.bak-*` backup first. To undo, copy the backup over `.env`
and run the restart again. Video uses Runway `gen4.5` when `RUNWAY_API_KEY` is set.

## GPT-5.5, 5.6 and 6.x support (AI engine update)

Newer OpenAI models refuse two things DHANZ normally sends: a temperature other than 1, and
function tools on `/v1/chat/completions` unless `reasoning_effort` is `none`. The OpenAI adapter
now learns this from the provider's own HTTP 400 reply and sends the request again with the
setting changed (once per model per process; nothing is shown to the user). Separately, when a
model refuses a request before answering (HTTP 400/404/422), DHANZ tries the next model instead
of failing the chat.

The live API image predates this, so install it with the deploy script (it only replaces three
AI engine files inside the running image and keeps a rollback image):

```bash
cd ~/DhanzAI && git pull
python3 scripts/server/deploy_ai_engine.py            # check: every file must be a repository version
python3 scripts/server/deploy_ai_engine.py --apply    # build, test, switch, health check
sudo python3 scripts/server/upgrade_models.py         # report: now tests GPT-6 the same way
```

`--apply` prints the rollback command
(`python3 scripts/server/deploy_ai_engine.py --rollback dhanz-api:rollback-<time>`).
A future `docker compose pull` of the published image replaces this local image; re-run the
script afterwards if the published image is older.
