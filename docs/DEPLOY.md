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

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f api      # migrations run automatically
curl https://dhanz.example.com/api/v1/health/ready          # {"status":"ok", ...}
```

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
