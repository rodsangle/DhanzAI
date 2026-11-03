# Send the instruction and file together

Attach/drop a file, type the instruction, and press Send once. The updated composer
registers file selection and byte reading immediately. The message queues until the
file upload and server extraction complete, then text and attachment IDs are sent
together. The draft stays visible while waiting. Cancel pending send keeps files
available for an explicit retry. Failed files are shown; retry them or deliberately
remove their failed chips before sending. A file-only send asks for the desired task
instead of silently choosing a summary.

Changing chat, project or account cancels pending sends. Late uploads cannot attach
to a different draft or make its upload counter negative. A queued request captures
the model, web mode and project at Send time. No failed message is auto-retried.

For conversion/extraction requests the backend provides extracted text in order,
bounded by the selected model and a 160,000-character cap. Ordinary questions retain
ranked retrieval. If content does not fit or OCR has missing pages, instructions
explicitly prohibit claiming a complete conversion. OCR does not guarantee correct
table reconstruction, handwriting, signatures or spreadsheet cell alignment.

## Existing custom AWS installation

The public backend schema is older than the custom AWS 0010 image. Do not replace
that image with the full public backend. `deploy/updaters/prepare_attachment_fix.py`
checks a known baseline attachment reader by its parsed AST, verifies the research
interface, and patches only that reader and two research call sites. Other custom
functions, existing tools, prompts and database code remain intact. Unexpected
source or source bind mounts cause a refusal before building/restarting anything.

Run it without arguments to prepare a derived image and import smoke test only.
`--apply` recreates only the API using every original Compose file plus its final
`docker-compose.attachments.json` overlay, preserving the existing OCR overlay.
The previous image and source are saved. Finish active replies/generations first.
Check `/api/v1/health/ready` afterward. No migration is added by the update.

`deploy/updaters/install_web_update.py` downloads the compiled preview web ZIP and
checks its SHA-256 before staging. It verifies the live Caddy bind mount and refuses
uncommitted Flutter source changes. `--apply` backs up the current browser build,
updates files atomically with the entry page last, and preserves the web directory
inode so Caddy continues seeing its mounted directory. Existing assets are retained
for open tabs; refresh with Ctrl+Shift+R. API, database, credentials and Caddy
configuration are not changed by this web helper. No Android APK is installed.

The helper only stages by default. For rollback, copy the saved browser build's
contents back into the existing web directory. For the API, use the preserved
Compose files without the final attachment overlay to return to the previous image.

## Validation

Flutter tests hold file reading and upload/extraction futures open, queue Send,
and verify the exact prompt and attachment IDs in one request. They cover failures,
duplicate Send, cancellation, chat/project/account changes and draft retention in
the actual composer. Backend tests check all 13 OCR page markers, bounded partial
coverage, attached-but-unreadable text, and a real XLSX download through a provider
stub's tool call. These tests verify the data/tool pipeline, not live-model OCR or
table-extraction accuracy. Deployment tests cover custom-code preservation, archive
path/symlink rejection, backups and Caddy's bind-mount directory identity.
