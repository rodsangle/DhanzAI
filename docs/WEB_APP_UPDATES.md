# GitHub updates for the installed web app (0.10.0)

Android installed Dhanz from its website. This feature updates that PWA and the
Edge browser app; it does not silently install an Android APK. Native installer
handling is unchanged.

## One-time AWS setup

Finish uploads and active replies/builds, then run the published
`deploy/updaters/install_web_updates.py --apply` on the existing AWS server.
It adds authenticated web-update routes to an image derived from the current
custom API, without a database migration or replacement configuration. Offline
checks run before activation, and an API image rollback command is saved.

The setup preserves the paired companion's token and existing tasks, adds the
fixed `update_web` recipe, and installs the checked GitHub web release. It keeps
the Caddy wrapper, API settings, knowledge library, weather, OCR and search.
The companion reads its updated configuration on its next poll; it must be running.

For the first phone refresh, open:

`https://dhanzai.com/app/update.html`

Tap **Refresh installed app**. This page loads outside the old Flutter app and
can replace its cached assets even when the old app lacks the new Update button.
Sign-in storage is kept. Return to the installed app and confirm version 0.10.0.

## Using Update

Open **Settings → App update → Update**. The button always checks the public
GitHub web channel again. If AWS already serves that build, any signed-in user
can refresh their installed app. If the server needs the newer build, only an
account owning a paired host with the advertised updater recipe can enqueue it.
Other users receive an explanation that the host owner must deploy first.

The authenticated manual click grants one execution of that exact advertised
recipe, expiring after five minutes. It does not create a permanent permission
or give models a tool to create update grants. Concurrent clicks/devices reuse
the existing queued/running task; ambiguous retries reuse a request key. Results
are account-owned and retained in Connected operations. No arbitrary command,
repository URL or filesystem path is accepted from the browser.

After actual completion, the phone refreshes. Active uploads block refresh; if
new uploads began while the server updated, finish them and press Update again.
Save unsent text before updating. The refresh unregisters only the applicable
Flutter workers and removes only this app's Flutter response-cache entries.
It preserves account localStorage/IndexedDB and unrelated service workers/caches.
The real loader URLs are fetched with HTTP cache reload before navigation, not
just cache-busted copies of a version file. The served version is checked so an
older server build cannot be reported as a successful new update.

## Publication and validation

The web-only `web-update-channel` GitHub prerelease carries `latest-web.json`.
It points to a checked versioned `web-updates-X.Y.Z-preview.N` release with the
compiled ZIP, checksum and public manifest. The manifest contains protocol,
version/build, release/asset names, SHA-256 and source commit. Download URLs are
derived exclusively from `rodsangle/DhanzAI`, never supplied by a client.

The named host updater validates ZIP size, SHA-256, safe paths and symlinks,
version, source commit and protocol. It stages privately, checks the live Caddy
mount/fingerprint, backs up the web client, and changes only nested static assets.
It refuses version/build downgrades and incompatible protocols. The host updater
and validator files themselves are pinned in the local recipe's verified-files
hashes. Public release trust rests on this repository's GitHub publication access.

The workflow publishes only after cache tests, Flutter analysis/tests and web
compilation pass. A promotion gate runs before touching release assets: older or
identical version/build reruns cannot overwrite the current channel or its ZIP.
For a new build, increment the app version/build, `WEB_VERSION`/`WEB_BUILD`, package
metadata and the versioned release tag as appropriate. Breaking updater/backend
requirements need a new protocol and explicit backend setup; they are not silently
applied as static web updates. No native release channel is replaced.
