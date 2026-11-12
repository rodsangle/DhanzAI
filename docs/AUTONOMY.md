# Account discretion setting

Use discretion is an account-owned response and coding preference, stored as the
`dhanz-autonomy` saved-skill record. It is injected into the chat turn context
without relying on the model to read an extra skill. It applies even with saved
memories off or in temporary chats; it does not load or create memories. Other
accounts are unaffected. The record is omitted from the chat skill catalog to
avoid a redundant tool call.

Enabled behavior: choose routine defaults, use already provided requirements,
read relevant context, start a focused build, preserve originals, and report
actual status. Ask only for blockers such as an ambiguous project/repository,
missing credentials or required authority. Existing tool limits, local-only
routing, account limits, rate limits, and grant checks still apply. The setting
does not grant merge, deployment, purchase or destructive-action authority.

Chat has a sparkle toggle on wide layouts and Chat options > Use discretion on
phones. Chat with Codex has a sparkle toggle. Both save the same account setting.
Codex can select routine runtime/model/branch defaults, inspect up to two common
source folders, include at most twelve relevant text files, and queue the draft
without the routine Start coding confirmation. Named or uniquely determined
repository targets are supported; ambiguous targets remain a question. A user
request is still needed: status messages and acknowledgements do not create a
new build. A fresh preference check happens before automatic queuing. One bounded
automatic repair can be selected; auth, quota and access failures are not replayed.
Publication remains under existing standing grants or explicit review.

The generator applies the preference to owned app, agent and repository jobs
without changing the stored source request. Existing mobile/revision markers are
retained. The normal generation protocol, validation and worker are preserved.

The combined install_autonomy.py --apply updater validates/stages the checked
web 0.10.5+ browser release, adds only autonomy.py and a guarded startup hook to
the running API image, enables the preference for the selected active account,
and installs the browser assets. Multiple accounts require a sign-in email.
Private account-setting backups and API/web rollback commands are printed.
No token permissions or grants are added; saved Replica/email skills, OCR,
connections, original projects and data are preserved. Subsequent model work
uses the configured API and may incur usage charges.
