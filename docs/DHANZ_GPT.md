# Dhanz GPT (gpt.dhanzai.com)

Dhanz GPT is a second web app from DHANZ AI: chat with streaming replies, pages (documents you write
with the assistant), projects, custom assistants, image generation, voice dictation, scheduled tasks,
share links and connected apps. Its source is `apps/dhanz_gpt` (Next.js 16, TypeScript, PostgreSQL).

It runs next to the main DHANZ AI service on the same AWS server and **changes nothing in it**:

| | Dhanz GPT | main DHANZ AI service |
| --- | --- | --- |
| address | `https://gpt.<domain>` | `https://<domain>` (unchanged) |
| container | `dhanz-gpt` (port 3000, internal only) | `api`, `caddy`, … |
| database | `dhanz_gpt`, role `dhanz_gpt`, same PostgreSQL server | `dhanz` |
| files | volume `dhanz-gpt-data` | its own |
| backups | `dhanz-gpt-backup` container → the same `./backups` folder | `backup` |
| sign-in | DHANZ AI accounts, checked by the API | — |

## Sign-in

There are no separate accounts. People sign in with their DHANZ AI email and password, and the same
two-step verification (authenticator app or emailed code). Dhanz GPT sends those to the API
(`/api/v1/auth/login`, `/auth/mfa/verify`) over the internal Docker network and keeps the resulting
tokens encrypted (AES-GCM with `APP_TOKEN_KEY`) in its own database. Every five minutes it checks the
account with `/users/me` (refreshing the token once if needed, under a lock so parallel requests
don't trip the API's refresh-token reuse detection). If DHANZ AI signs the person out, disables or
deletes the account, the Dhanz GPT session ends too. Signing out of Dhanz GPT also signs that device
out of DHANZ AI.

- Unverified email: refused, with a message to verify in DHANZ AI first.
- New accounts: created only in DHANZ AI (the sign-in page links there).
- Each account gets its own private workspace ("one workspace per account"); nobody sees anyone
  else's chats, pages or files. Administrators can't read private chats either.

## Install or update (on the server)

1. **DNS.** Add a record for `gpt.<domain>` pointing at the server (an `A` record with the same IP as
   `<domain>`, or a `CNAME` to `<domain>`). Caddy gets the HTTPS certificate on the first visit after
   it resolves.
2. **Check** (changes nothing, prints what it found, including DNS and which AI keys it will reuse):

   ```bash
   cd ~/DhanzAI && git pull
   python3 scripts/server/deploy_dhanz_gpt.py
   ```

3. **Install:**

   ```bash
   python3 scripts/server/deploy_dhanz_gpt.py --apply
   ```

   It builds the image from `apps/dhanz_gpt` (a few minutes), creates the database and role if missing
   (never touching existing data), creates the `vector`, `pgcrypto` and `pg_trgm` extensions there,
   runs the app's migrations, starts the container, waits for `/api/health`, adds the backup container,
   then adds the `gpt.<domain>` block to the Caddyfile (copy kept as `Caddyfile.bak-<time>`), validates
   it and reloads Caddy. If the health check fails the previous container comes back; if Caddy refuses
   the block the old Caddyfile is put back.

Re-running `--apply` is how you update: same steps, new image tag, data kept.

**Go back** to the previous version (the command is printed after each update):

```bash
python3 scripts/server/deploy_dhanz_gpt.py --rollback dhanz-gpt:20261119-101500
sudo docker images dhanz-gpt        # the images kept on the server
```

**Remove** the app (keeps the database, files, secrets and backups):

```bash
python3 scripts/server/deploy_dhanz_gpt.py --uninstall
```

## Settings and secrets

Generated once and kept in `~/.config/dhanz-gpt/dhanz-gpt.env` (mode 600): the database password and
`APP_TOKEN_KEY`. Don't lose that file: without `APP_TOKEN_KEY` stored sign-ins and connected-app
tokens can't be decrypted (people simply sign in again; connected apps need reconnecting).

`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` are copied from the running API's settings at every
`--apply`, so Dhanz GPT uses the same provider accounts. Nothing is printed.

Optional, not set by the script (add them to the secrets file and re-run `--apply` once supported):
email sending (`RESEND_API_KEY`: without it, emails such as scheduled-task results are kept in the
app's outbox instead of sent) and web push (`VAPID_*`: without them, browser notifications stay off).

## Backups and restore

`dhanz-gpt-backup` writes `backups/dhanz-gpt-YYYYmmdd-HHMM.dump` daily (14 days kept) and
`backups/dhanz-gpt-files-YYYYmmdd.tgz` weekly (4 kept), in the same folder as the main backups.

Restore the database into a fresh `dhanz_gpt` database:

```bash
sudo docker exec -i <db container> pg_restore -U <POSTGRES_USER> -d dhanz_gpt --clean --if-exists < backups/dhanz-gpt-….dump
```

## Health and logs

```bash
sudo docker logs --tail 100 dhanz-gpt
sudo docker exec dhanz-gpt node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>r.text()).then(console.log)"
```

`/api/health` answers `{"ok":true,"migrations":10,"auth":"dhanz"}` when the database is reachable.

## Known limits

- The API records the sign-in IP from `X-Forwarded-For`. If its uvicorn only trusts Caddy's address,
  sign-ins through Dhanz GPT show the Dhanz GPT container's IP in DHANZ AI's sign-in alerts instead of
  the visitor's. Harmless; fix by adding the Docker network to `--forwarded-allow-ips`.
- Rate limits for sign-in attempts are per container (in memory); a restart clears them.
- The name contains "GPT", which people closely link with OpenAI. Get a trademark lawyer's view before
  marketing the name widely.

## Development

```bash
cd apps/dhanz_gpt && npm ci
npm run dev                 # local dev sign-in, demo model (see README)
npx playwright test         # end-to-end suite: three servers incl. a stand-in DHANZ API
```

CI (`Dhanz GPT` job) runs lint and types, builds the image and boots it against a fresh PostgreSQL set
up by the deploy script's own bootstrap SQL.
