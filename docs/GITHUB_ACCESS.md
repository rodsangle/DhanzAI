# GitHub access from Dhanz

The backend has outbound internet access independently of search-provider setup.
These tools add GitHub API access; they do not enable arbitrary browsing, execute
repository code, or require opening an inbound firewall port.

## Configure on the backend only

```dotenv
GITHUB_ALLOWED_REPOSITORIES=rodsangle/DhanzAI
GITHUB_WRITE_ENABLED=false
```

Repository names are an exact comma-separated allowlist. Without a configured
allowlist the tools are hidden and refuse execution. Only active administrator
accounts may use the server's GitHub integration, including public reads.
Other accounts cannot borrow the administrator's token.

Public repositories can be read without a token (GitHub rate limits apply).
For private repositories, create a fine-grained personal access token in GitHub
Settings → Developer settings → Personal access tokens. Select only the intended
repositories. Start with **Contents: read-only**. Organization repositories may
require owner approval or SSO authorization. Store the token as `GITHUB_TOKEN`
in the server's protected `deploy/.env`, never in chat, a browser build or Git.

For edits and draft PRs, grant **Contents: read and write** and **Pull requests:
read and write**, then set `GITHUB_WRITE_ENABLED=true`. Metadata permission is
normally included by GitHub. Do not grant unrelated administration permissions.
Token expiration and rotation remain the server owner's responsibility.

Recreate the API with the complete set of deployment overlays after changing
environment settings. A restart alone does not refresh Compose's injected values.
The new source must be installed first: changing `.env` does not add tools to an
older image. Preserve custom synced/local-media/direct-tool overlays on the
user's deployment. Do not replace that image with an older repository build.

## Use

Choose a tool-capable model and ask:

- “List the root files in rodsangle/DhanzAI.”
- “Read README.md at main in rodsangle/DhanzAI and explain the setup.”
- “Create dhanz/fix-description, update the README description, and open a draft PR.”

The tools can list one directory, read text files up to 64 KiB, create a
`dhanz/...` branch, commit an existing or new text file, and open a draft PR.
Existing-file edits require the exact blob SHA from a fresh read on the target
branch. Conflicts stop instead of overwriting concurrent edits. Default-branch
writes, merges, deletion and arbitrary shell commands are not provided.
Commits can trigger repository CI; users should request changes deliberately.
Multi-file edits use separate commits, not an atomic transaction. A completed
commit remains on its branch if a later step fails. The assistant should report
partial outcomes and must not blindly repeat successful writes.

Directory results are nonrecursive, capped at 200 returned entries, and disclose
GitHub's own 1000-entry Contents API limit. Large files, binary files and reported
symlinks/submodules are rejected. Use smaller directories/files for large repos.
An HTTP 404 may mean either a missing resource or inaccessible private repository.
Redirects are rejected, so allowlisting a renamed repository requires an update.

Repository text is untrusted reference data. It must not supply instructions to
reveal credentials, access other repositories or authorize writes. Retrieved
private code is sent to the selected model as tool output and may be retained in
chat history; use this feature only with a model/provider approved for that code.

## Validation and limitations

Automated tests use simulated GitHub responses, including token forwarding,
public access, role enforcement, repository boundaries, stale SHA conflicts,
branch restrictions, sanitized errors and draft PR payloads. No live repository
was changed during implementation. Live token permissions, organization policy
and the custom AWS image must be verified during deployment.

Test read access first; then explicitly request a small edit on a test branch
and inspect the draft PR in GitHub. Do not treat a configured token or the general
API health check as proof that GitHub requests or writes succeed.

## Existing custom AWS deployment

A separate additive installer was prepared in the task workspace as
`/workspace/dhanz-update/prepare_github_tools.py`. It checks the previously
reported assistant-tools checksum, rejects conflicting source mounts, tags a
rollback image, and builds on the running API image. It appends tool registration
instead of replacing existing creative, skills, PC-control or direct-tool logic.
Its compatibility adapter reads the three GitHub variables from the process
environment, so it need not replace the custom Settings class. The installer
only prepares an image and `deploy/docker-compose.github.yml`; it does not
restart production or configure credentials.

After successful installation and secure configuration, preserve all prior
overlays and put the GitHub overlay last:

```bash
cd ~/DhanzAI/deploy
sudo docker compose -f docker-compose.prod.yml -f docker-compose.web.yml -f docker-compose.synced.yml -f docker-compose.local-media.yml -f docker-compose.direct-tools.yml -f docker-compose.github.yml up -d --no-deps --force-recreate api
```

Rollback uses the same command with `docker-compose.github.yml` omitted, restoring
the existing direct-tools image. Keep the `dhanz-api:before-github` image too.
No data migrations are required. The installer has not run on AWS in this task.
