# Draft spelling and device autocorrect

The composer now has a Spelling options menu beside Attach files:

- Device autocorrect enables/disables the TextField's native autocorrect and
  suggestion flags for the current composer. Availability, dictionaries and
  actual automatic replacement depend on the browser/keyboard/OS. Turn it off
  when entering code or other exact text. This does not install a system-wide
  dictionary or force browsers to autocorrect.
- Review spelling fixes offers a small offline set of common English typo fixes.
  It shows the original and suggested draft before Apply; Cancel leaves the draft
  unchanged. An Undo action restores the original if no later edits have occurred.
  No correction is sent as a chat message automatically.

The offline review protects fenced code, inline-code lines, common raw structured
input/commands, URLs, emails, paths and compound identifiers. Its dictionary is
intentionally limited: no suggested fixes is not a claim of error-free writing.
It is not a general grammar checker, paraphraser or multilingual spelling engine.
The preview is the review step for names/technical text not recognized by those
heuristics. It refuses to overwrite a draft edited while the dialog was open.
Queued drafts disable the menu where the existing composer has queued-send state.

No Dhanz AI provider request is made for typo review. Native device/browser
spelling features are controlled by that device and may themselves use online
services. The toggle is local composer state, not an account-wide saved preference.

## Custom AWS installation

`deploy/updaters/install_chat_controls.py` builds from the current AWS Flutter
source. It adds spelling controls and the already-tested read-aloud controls (or
recognizes an identical existing installation). It changes only their imports,
composer flags/button/field and assistant action button. Unknown layouts and
custom implementations are refused rather than overwritten.

A known live Local News feature is protected: if the current browser JavaScript
contains Local News but the source lacks it, the helper refuses to rebuild. The
source must represent the installed application; it cannot reconstruct other
compiled-only customizations. No checkout of an older public frontend is used.

Without --apply it stages/tests/builds only. With --apply it installs only after
analysis, all targeted widget tests and a release browser build succeed. The live
browser assets and edited source files are backed up, Caddy's bind-mount root
inode is preserved, and concurrent source/browser deployments cause refusal.
API, SearXNG, weather, OCR, database, keys and Caddy config are unchanged.

After success, refresh dhanzai.com with Ctrl+F5. Use Spelling options → Review
spelling fixes on `teh messege` to preview `the message`; apply/cancel/undo as
needed. A speaker under a finished assistant reply starts/stops read aloud.
This installs the web client only. Native Android/Windows apps need rebuilt
native releases to receive the same source changes.

Validation: eight isolated Flutter spelling tests plus targeted analysis passed
on the cached SDK. Six portable updater checks cover source patching, queued
state, idempotence, bundled files and preserving Local News. Read aloud retains
its earlier five passing widget tests. The AWS updater must additionally pass
analysis/tests and the full browser build against the actual deployment SDK and
lock before it changes the live site; local full web compilation remains blocked
by the missing cached web SDK artifacts, as recorded in READ_ALOUD_AND_SEARCH.md.
