# Themes and bundled assistant skills

## Appearance

In the updated Flutter client, open **Settings → Appearance** and select Midnight
Gold, Arctic Light or Aurora Teal. Theme previews use the actual palette. The
selection applies throughout the app and is saved using its existing secure
preference store, without adding a dependency.

Original Dhanz remains available with Dark, Light and Follow system modes. Existing
`theme_mode` values are preserved unchanged; the new `theme_style` preference only
appears when a user selects a skin. Unknown new style values fall back to Original.
The separate Follow system skin switches between Arctic Light and Midnight Gold
when the device changes brightness, without a schedule or restart.

The original logo remains a brand mark. Code-block backgrounds and voice accents
follow the active palette. QR authentication images remain black/white for scanning.

## Published skills pack

The exact `dhanz-general-assistant` v1.0.0 pack published earlier is bundled as
package data inside `dhanz-ai-engine`. The portable Markdown remains in `skills/`;
a consistency test checks that both copies match. A built wheel includes the data,
so production does not rely on a repository checkout or download skills at runtime.

Normal chat requests include the master instructions and at most two relevant
workflow references selected from the bounded bundled list. Unmatched or
non-English requests retain the master rules plus writing guidance. Keyword routing
is a context-size optimization, not a language or intent classifier. User messages
are never interpolated into these trusted skill instructions or used as file paths.

`ASSISTANT_SKILL_PACK_ENABLED` defaults to `true` in the updated source backend.
Set it to `false` and restart the updated API to use its previous prompt behavior.
The pack supports writing, research, coding/GitHub, document coverage, calculations,
creative jobs and approved PC actions. It grants no tools or access, adds no OCR or
layout-preserving PDF engine, and changes no local confirmations. Tools and privacy
controls remain authoritative. Extra instructions consume some model context/tokens.

Custom Dhanz installations with a Skills editor can still import the portable pack
using its README. Avoid adding it twice if the backend already bundles it.

## Verification and builds

Flutter tests cover theme selection, saved preferences across a fresh provider,
legacy light/dark/system behavior, unknown preferences, delayed loads and saves,
device brightness changes, narrow layouts at large text sizes, and text/button
contrast in the three new palettes. Run with the pinned Flutter version:

```sh
flutter pub get --enforce-lockfile
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test --dart-define=DHANZ_THEME_SCREENSHOTS=true
flutter build web --release --no-web-resources-cdn
```

The screenshot flag writes actual rendered appearance-picker images into
`build/theme-previews`. CI uploads them with the web build after successful checks.
These are widget previews, not screenshots of the live AWS website.

AI-engine tests exercise all seven workflows, bounded selection, injection/path
isolation, portable/bundled consistency and prompt opt-out. A backend test verifies
that the document workflow reaches a real chat request sent to the provider stub.

## Deployment boundary

No database migration, provider key change or extra dependency is needed. Themes
need an updated frontend; runtime skills need the updated backend and AI engine.
Neither takes effect on an already running deployment merely by downloading source.

The current AWS image has custom features and migration 0010, beyond the public
checkout. Do not replace that backend with this older public image. Port the skills
integration into its matching source, retain its prompts and permissions, and test
before recreating its API. Import through its existing editor when that is safer.

For a frontend deployment, preserve the current build directory and Caddy mounts,
test the new build against the existing API first, and keep the old frontend for
rollback. Switching the frontend does not require replacing the API or database.
