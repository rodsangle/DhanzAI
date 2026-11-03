# DHANZ AI update preview — 2026-11-03

This preview publishes the changes prepared in the development workspace. It is
not an automatic upgrade of dhanzai.com, an Android store release, or a replacement
for the custom AWS 0010 image. The stable application version remains unchanged.

## Included

- Windows control panel with enlarged topmost approval dialogs, explicit selected
  window, mouse/keyboard support, opt-in bounded automatic navigation, stop controls
  and a screenshot-based task client. Windows execution requires local setup/testing.
- Authenticated, opt-in stateless screenshot planner with no database migration.
- Deterministic calculator/unit shortcuts and scoped GitHub tools for the public
  backend source, plus targeted custom-image preparation scripts.
- Private optional Ollama service profile and setup documentation. It is not enabled
  on AWS and is not recommended as a speed improvement on the 4-GB instance.
- Background image/video progress tracking across chats, durable-job regression
  tests, account isolation and gallery links.
- Original general-assistant skills pack with writing, research, coding, document,
  calculation, creative and PC-task workflows. Import it through a supported Skills
  editor; it does not enable missing tools by itself.
- Theme mockup and Claude brief for Midnight Gold, Arctic Light and Aurora Teal.

## Validation and limits

Local validation included a full backend run (251 passed, 2 PostgreSQL-only tests
skipped), 15 final planner checks, and 41 portable companion checks (native DPAPI
skipped on Linux), plus Python lint/formatting and Dart 3.13.7 syntax/formatting.
Native Windows capture/input still requires a real PC smoke test. The pinned
Flutter 3.47.8 runtime was unavailable locally, so Flutter analysis, widget tests
and compiled web/app builds were not claimed as passed. Publication workflows run
their own checks; inspect their outcomes before using generated artifacts.

The themes are concepts, not implemented selectable themes. Exhaustive PDF OCR and
layout-preserving document reproduction were discussed but not implemented; the
skills pack describes honest coverage reporting, not a new PDF engine.

## Downloads

The update-bundle workflow publishes source, Windows helper source, server updater
scripts, skills, theme concepts, a manifest and SHA-256 checksums. Separate build
jobs may add a web build and unsigned Windows helper executable only after their
checks succeed. No APK is promised without the existing Android signing key and
a successful native app build. Source packages are not installable Android apps.

Use `SHA256SUMS.txt` for the source packages; later compiled artifacts have their
own `.sha256` files. The release stays a prerelease and does not publish a stable
`latest.json`, change `api:latest`, merge main, or deploy AWS.
