# Reply read-aloud and web search on the custom AWS deployment

These features have separate installations. A saved skill alone enables neither.

## Read aloud

A speaker button beneath finished assistant replies starts speech; clicking Stop
or another reply stops the previous reply. Speech also stops when its message
widget leaves the tree or the app goes into the background. Speech is never
started automatically and does not require microphone permission.

The existing `flutter_tts` plugin uses browser/OS voices. Dhanz does not send a
speech-generation request to its AI provider. Some system voices may themselves
use network services; this is not a guarantee of entirely offline speech.
Availability and language quality depend on installed voices and browser support.
Failure shows an availability message and permits retry. Code blocks are described
as available on screen; prose is split into utterances rather than truncated.

`deploy/updaters/install_read_aloud.py --apply` makes a private staging copy of
the AWS machine's current Flutter source, patches only the assistant action row,
and adds the speech widget. The source layout and existing plugin must match;
otherwise it stops without installing. It preserves source changes outside this
patch and refuses deployment if source changes during the build.

Before touching live static assets it runs dependency resolution with the current
lock enforced, targeted analysis, read-aloud tests and a release browser build.
It then backs up the live browser build and preserves the root directory inode
used by Caddy's bind mount. The frontend source should represent the current
installed browser application: compiled-only customizations absent from that
source cannot be reconstructed by this updater.

API image, secrets, database, weather, OCR and Caddy configuration are unchanged.
This installs the browser client; existing native Windows/Android installations
need their own rebuilt release. Refresh the browser (Ctrl+F5 on Windows) after
installation. A backup path is printed for rollback assistance.

## Web search

Existing search adapters support Tavily, Brave Search and SearXNG. Tavily/Brave
require their own provider account/key; an OpenAI key is not a substitute.
Provider quotas and billing apply according to the selected account's plan.
Review current provider terms rather than assuming unlimited free search.

Use `deploy/updaters/configure_web_search.py --provider tavily --apply` (or
`--provider brave`) directly in the interactive AWS terminal. The key prompt is
hidden. Never paste the key in chat. The helper updates only SEARCH_PROVIDER and
the selected provider's key in the existing `.env`, and stores a private backup
outside the repository. It does not print credentials or resolved Compose config.

An additive Compose overlay pins the same running API image and references the
key through ordinary `.env` interpolation, preserving compatibility with other
updaters. All prior Compose files remain active. Only the API is recreated. After
health is confirmed, the helper performs a real provider search and prints only
its provider/result status. Configuration presence is not treated as success.
A private disable-search command is saved alongside the backup.

Enable the chat's Web search control if present. Account privacy settings and
existing search consent still apply. Queries leave the server for the selected
search provider. Existing fetched-page robots/SSRF rules remain in force.
This does not provide PC control, bypass authenticated sites or install SearXNG.

## Checks

Portable helper tests:

```bash
python -m unittest discover -s tests -p test_read_aloud_installer.py -v
python -m unittest discover -s tests -p test_search_configuration.py -v
```

The read-aloud widget has targeted Flutter tests in `test/read_aloud_test.dart`.
The AWS installer reruns those and compiles against the deployment's actual SDK
and dependency lock before it installs. Device voices still require a real
browser/device check. Search needs a live key/provider check during installation.

Validation for this update: five isolated Flutter tests and targeted analysis
passed, plus six frontend-updater and two search-configuration checks. The local
browser compilation could not complete because the cached SDK lacked its web
artifacts and the official artifact download was unavailable in this environment.
The installer therefore requires a successful full build on AWS before deployment;
actual voice output and search credentials remain installation-time checks.
