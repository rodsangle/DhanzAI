# Matching Dhanz 0.9.3 client controls

This app is based on the user-supplied 0.9.2+20 Flutter source, not the older
0.8.0 checkout. It preserves that client's Local News, prompt queue, microphone,
Creative Studio and existing shared read-aloud implementation. Its changes are
the offline spelling menu/device autocorrect flags, stable speech-button message
keys and the 0.9.3+21 version bump. No server API or database is replaced.

The dedicated client-controls workflow resolves the existing lock with Flutter
3.47.8, analyzes this client, tests its controls and compiles with /app/ as base.
Only a successful build is packaged and published as a separate web prerelease.
It does not publish native apps, stable update manifests or Docker images.

The browser/Android installed web app receives the same hosted client. Native
browser speech voices determine read-aloud availability. Spelling review is a
limited offline English typo helper with preview, Cancel and Undo; device
spelling suggestions depend on browser/keyboard support. No new paid API key is
needed. User/device speech services may themselves require a network connection.

Use deploy/updaters/install_pwa_controls.py from the repository to install the
compiled prerelease after it exists. It verifies the exact 0.9.2 deployment ID
and source hash and keeps the outer PWA wrapper and backend services intact.
The repository's older generic source-build updater is not the installer for
this release. Keep this client source for future builds so the controls persist.
