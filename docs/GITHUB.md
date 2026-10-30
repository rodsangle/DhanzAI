# GitHub repositories in DHANZ AI

This integration is read-only: browse selected repositories, read source files, list open
issues and pull requests, and ask Dhanz to explain code or suggest improvements in chat.
It cannot push commits, create branches, open PRs, post reviews, merge, or execute code.
It supports GitHub.com, not GitHub Enterprise Server. It is separate from the GitHub
connection used by Codex to maintain DHANZ AI itself.

## Enable the backend

For the local Windows checkout, run from the project folder:

```powershell
.\.tools\backend-venv\Scripts\python.exe scripts\setup_github.py
```

This helper backs up an existing SQLite database under the ignored `.tools` directory,
applies migrations, and writes a new encryption key to `backend/.env` only when none is
configured. It preserves a valid existing key and does not print it. Restart the backend
afterward. It does not connect a GitHub account or restart running services automatically.
Use the manual steps below for a hosted/production backend.

1. Back up your backend database and apply `alembic upgrade head` from `backend/`.
   Migration 0008 adds only the per-account `github_connections` table.
2. Generate a Fernet key once with your backend Python environment:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
3. Set `GITHUB_TOKEN_ENCRYPTION_KEY` in the backend's private `.env` or secret manager.
   Keep it stable across restarts and API replicas. Never commit it. Losing or replacing
   the key requires users to reconnect; it does not change their repositories.
4. Restart the backend and use a client build that contains **Settings → GitHub repositories**.
   The GitHub screen is included in the 0.8.0 client; the earlier 0.7.0 installer does not contain it.

Use HTTPS for a remote backend. The client permits HTTP only for localhost/loopback development.
The backend's existing `ASSISTANT_TOOLS_ENABLED=true` and a model with tool support are required
for GitHub questions in chat. Browsing still works without an AI key. Standalone local Ollama
chat does not use the backend connection; sign in to backend account mode to use it.

## Connect your repositories

1. Open GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens**.
   [Create a token](https://github.com/settings/personal-access-tokens/new) with an expiration.
2. Choose your repository owner and **Only select repositories**. Select the repositories
   you want DHANZ to read. For organizations, approval or SSO authorization may be required.
3. Give **Contents**, **Issues**, and **Pull requests** **read-only** permission. GitHub
   includes Metadata read access. Do not grant write or workflow permissions.
4. In DHANZ **Settings → GitHub repositories**, paste the token into the hidden token field.
   Enter repository names, for example `rodsangle/DhanzAI`, one per line (up to 20).
5. Review the disclosure that code used in chat is sent to your selected AI provider and
   may remain in chat history. Select the checkbox and save. The token field is cleared.
6. Select a repository, browse a folder or read a file, then **Ask Dhanz to explain this**.
   For reviews, open **Pull requests**, select a PR and **Ask Dhanz to review this PR**.

Example chat requests:

* “Use GitHub to explain the structure of rodsangle/DhanzAI.”
* “Read backend/app/services/github_service.py in rodsangle/DhanzAI and suggest improvements.”
* “Review pull request #12 in owner/repo. Cite affected files and explain possible bugs.”

Never paste a GitHub token into chat. Reconnect to replace an expired token or change the
repository selection. Disconnect deletes the saved token from the live database; backups
and existing chat answers may still contain historical data. Revoke the token on GitHub
to invalidate it everywhere. Account deletion cascades to its stored connection. Account
export contains connection metadata but never the encrypted or plaintext token.

## Limits and implementation

The API sends GET requests only to `https://api.github.com`, never follows redirects, and
never fetches raw download URLs or URLs supplied by symlinks/submodules. GitHub may resolve
an internal symlink to an ordinary file in its contents API. Every read checks the
user's selected repository and its stable GitHub ID. Tokens are Fernet-encrypted with an
owner-bound payload; they are never tool arguments or returned to the model. Data is isolated
by the authenticated DHANZ user. A request already in flight at disconnect may finish.

Reads have a 20-second HTTP timeout and a 2 MB response cap. UTF-8 source files are limited
to 128 KB, with up to 200 lines / 24,000 characters per read. Directory results are capped
at 250 entries; GitHub itself caps its contents API directory listings at 1,000. Lists and
PR file pages have explicit pagination. PR patches can be omitted by GitHub or shortened
by DHANZ and are marked incomplete. The assistant must disclose incomplete reviews.
Repository instructions are untrusted content. No code from repositories is executed.

Routes (all require DHANZ account authentication):

* `GET /api/v1/github/connection` — readiness and saved non-secret metadata.
* `PUT /api/v1/github/connection` — validate and replace a token and selected repositories.
* `DELETE /api/v1/github/connection` — disconnect.
* `GET /api/v1/github/read?operation=...` — repositories, directory, file, issues, pulls, pull.

The `github_read` assistant tool uses the same service and authorization. Read requests
are limited to 60/minute/account; connection attempts to 5/minute/account. Redis-backed
limits are shared when Redis is configured. GitHub's own quotas also apply.

References: [repository contents](https://docs.github.com/en/rest/repos/contents),
[pull requests](https://docs.github.com/en/rest/pulls/pulls),
[token authentication](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api).

## Verification (October 30, 2026)

* Flutter: 67 tests passed; static analysis clean, including token entry/clearing, consent,
  repository browsing, phone layout and HTTPS enforcement.
* Backend full workspace run: 210 passed, 2 skipped, one pre-existing web API test failed
  because local `WEB_SEARCH_PROVIDER` was enabled. That test passed when rerun with its
  expected `WEB_SEARCH_PROVIDER=none`. Coverage was 83.30% (80% gate passed).
* The separately added setup-helper test passed: database backup restored correctly,
  unrelated configuration remained intact, and the encryption key stayed stable and hidden.
* GitHub tests cover account isolation, token encryption and ownership binding, selection
  enforcement, account deletion/export, redirects and errors, response limits, text/PR
  pagination, rate limiting and the streamed chat/tool path. GitHub responses are simulated;
  no personal token was connected or real private repository accessed during testing.
* Migration 0008 upgrade → downgrade to 0007 → upgrade passed on an isolated SQLite database;
  Alembic found no model/schema differences.
* Windows 0.8.0 release and the in-place Inno installer built successfully. This local build
  includes the existing workspace edits. The running app and backend were not restarted or
  upgraded, and mobile builds and live AI/GitHub account validation were not performed.
