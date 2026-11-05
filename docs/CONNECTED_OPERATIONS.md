# Connected operations (0.9.8 preview)

Dhanz can read selected GitHub repositories through its existing encrypted connection,
publish coding drafts automatically under standing permission, and run named commands
on a paired Linux server. This is an additional connection, not a cloud subscription
or an AWS account administrator role.

## Install

Run `deploy/updaters/install_connected_operations.py --apply` on the existing AWS
host with the 0.9.5 coding backend installed. It derives an additive image from the
running custom API, keeps its environment and Compose overlays, backs up PostgreSQL,
and adds migration 0013. It does not replace the private backend with the public
repository's older image. The installer checks the new authenticated route and
prints the image rollback command. No grants exist and no server/repository action
is performed by installation. On image rollback, retain the additive tables.

Then install the matching compiled browser assets using
`deploy/updaters/install_pwa_operations.py --apply`. This preserves the Caddy wrapper
and nested `/app/` mount. Refresh Edge with Ctrl+F5; close and reopen the Android PWA.
Settings should show 0.9.8. No APK is required for the installed website.

## Pair the existing AWS host

1. In Dhanz's sidebar, open **Connected operations**. Create a pairing token for
   **AWS Dhanz**. The token is displayed once. Only its hash is stored in the API.
2. In the AWS terminal run:
   `python3 ~/dhanz-server-companion-setup/configure_aws.py`
3. Paste the token at its hidden prompt. Do not put it in chat or a command argument.
4. Run the three service commands printed by setup, separately. This enables an
   outbound-only systemd companion as the Ubuntu user, surviving logout/reboot.
   No inbound port, SSH private key or AWS access key is needed.
5. Refresh **Connected operations**. Authorize **health** and **restart** with the
   desired expiry and execution count. Each recipe shows its actual effect.

The default health recipe checks HTTPS readiness. Restart re-reads the active
Compose labels immediately before execution and recreates only the API using the
current image and overlays, never a stale saved configuration or a pulled image.

To enable **deploy**, select a specific reviewed Python updater already on AWS:

```bash
python3 ~/dhanz-server-companion-setup/configure_aws.py --approve-updater /absolute/path/to/reviewed_updater.py
```

Pairing setup asks for a token again. Reuse the existing private pairing token if
available, or disconnect and create a new connection. Then restart the companion
service and authorize the advertised deploy recipe. The updater file is pinned by
SHA-256. Changing it stops execution until locally reapproved and reauthorized in
Dhanz. This does not mean every future release is automatically trusted. An updater
may itself use the network and have broad host permissions; choose one you trust.

After setup, ask normal chat **“Check my AWS server health”**, **“Restart Dhanz”**,
or **“Deploy my approved update”**. The model lists available standing grants and
queues the matching named task. It cannot create or expand grants, change recipes,
or pass shell arguments. API and companion activity distinguish queued, executing,
completed, failed, cancelled and uncertain results. Command output is not uploaded.
The server checks exit status, not the semantic correctness of an updater's changes;
run a health check afterward. The page also provides **Run task now**.

## GitHub automation

Connect GitHub in Settings and select repositories first. Contents and pull-request
write permissions allow draft branches/PRs; workflows write permits the existing
workspace checks workflow. In **Connected operations**, enter an exact repository
and base branch, then authorize automatic draft publication with expiry and a limit.
The grant applies only to coding drafts created after authorization for that account,
repository identity and branch. Generate through **Chat with Codex** as usual.
Completed, validated files publish to a new `dhanz/...` branch and draft PR without
another confirmation. Existing stale-base checks, file validation and scoped GitHub
credentials still apply. Existing drafts do not suddenly publish. This does not
merge a PR or directly change the default branch. A deployment remains a separate
server recipe with a separate permission.

## Revocation and recovery

Revoke grants or disconnect the server from the page. These stop unclaimed work;
an action already started may finish. Stop all local execution with
`sudo systemctl stop dhanz-server-companion`. A companion token authenticates only
its server queue/results and cannot list chats, create permissions or read GitHub.
Store its private config under `~/.local/share/dhanz-server-companion` (mode 600).

Execution consumes a grant use once. A request key deduplicates ambiguous retries.
Server jobs are claimed once, and a durable local SQLite journal is written before
starting the command. Lost results do not cause execution to be replayed. Queued jobs
expire after five minutes; missing long-running results become uncertain after
35 minutes while the companion polls. Inspect the host/GitHub before intentionally
starting a new task after an uncertain outcome. The system does not promise exactly
once delivery across failures.

## Folder uploads and selecting replies

**Upload folder** in the browser opens a directory chooser, including nested files.
Before reading/uploading bytes, a review lists included paths and the count excluded
for common credentials and generated directories (`.env*`, `.git`, `.aws`, `.ssh`,
private-key extensions, `node_modules`, virtual environments and build output).
Review for other secrets; filename filtering cannot recognize every credential.
At most 200 files / 20 MB before compression are accepted. Cancel uploads nothing.

The files become one `.dhanz-folder.zip` attachment with original relative paths.
The backend validates archive sizes, paths, duplicates, encryption and symlinks,
reads in memory, and indexes supported text/Office/PDF contents with file boundaries.
OCR uses the existing configuration with a shared page/time budget per folder.
Images and unsupported members remain in the downloadable archive, with explicit
notes instead of invented content; upload images separately for visual analysis.
The archive is private to the existing knowledge library access controls. Folders
are data, never code to execute. Large contents remain subject to chat retrieval
and context limits. Unsupported directory selection on a mobile browser can fall
back to opening the site on Edge/Chrome on the PC.

Reply Markdown now shares one selection region across paragraphs and highlighted
code. Drag the mouse and press Ctrl+C or use the selection menu. Existing Copy,
Share, read-aloud and feedback controls remain available.
