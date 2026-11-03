# DHANZ AI themes and skills update preview — 2026-11-03

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
- The published general-assistant skills pack is bundled in the AI-engine package
  and used by normal chat requests in the updated backend, with writing, research,
  coding, document, calculation, creative and PC-task workflows.
  `ASSISTANT_SKILL_PACK_ENABLED=false` restores previous prompt behavior. It grants
  no tools or permissions. Custom Skills editors can import the portable pack.
- Working Midnight Gold, Arctic Light and Aurora Teal themes in Settings →
  Appearance, with previews and saved selection. Original Dhanz preserves existing
  light/dark/system preferences. Follow system switches between Arctic Light and
  Midnight Gold as device brightness changes.
- An OCR activation helper for existing custom Compose deployments. It preserves
  the current API image and configuration files, checks installed OCR tools, and
  enables OCR only when explicitly run with `--apply`. Re-upload PDFs afterward.

## Validation and limits

Local theme/skill validation includes 45 AI-engine tests with 91% coverage, real
chat-request integration checks, wheel package-data loading, Python lint/formatting
and Dart formatting. Flutter analysis, UI tests, screenshot capture and a release
web build run on the pinned Flutter 3.47.8 GitHub runner. Compiled artifacts are
attached only when those checks succeed; inspect the workflow outcome.
Native Windows capture/input still requires a real PC smoke test.

The original theme mockup is retained as a design reference. Rendered picker
previews are packaged separately after successful Flutter tests. Exhaustive PDF
OCR and layout-preserving document reproduction were not implemented; the skill
gives honest coverage guidance, not a new PDF engine.

## Downloads

The update-bundle workflow publishes source, Windows helper source, server updater
scripts, skills, theme concepts, a manifest and SHA-256 checksums. Separate build
jobs may add a web build, theme previews and unsigned Windows helper executable only after their
checks succeed. No APK is promised without the existing Android signing key and
a successful native app build. Source packages are not installable Android apps.

Use `SHA256SUMS.txt` for the source packages; later compiled artifacts have their
own `.sha256` files. The release stays a prerelease and does not publish a stable
`latest.json`, change `api:latest`, merge main, or deploy AWS.

See `docs/THEMES_AND_SKILLS.md` in the source repository before deploying,
especially when using the custom AWS 0010 image.
