# Claude implementation prompt

Update DHANZ AI's Flutter app with three selectable themes matching the attached
`dhanz-theme-concepts.png`: Midnight Gold, Arctic Light, Aurora Teal.

Inspect existing themes, settings, state management and preference storage first.
Preserve unrelated changes and all application behavior. Use the palette in this
folder's README, adjusting shades for accessible text/control contrast.

Add previews in Settings, persist the choice, and retain Follow system (Arctic
Light during light mode, Midnight Gold during dark mode). Migrate existing
light/dark/system preferences without resetting other settings.

Use shared ThemeData, ColorScheme and component themes rather than scattered
hard-coded colors. Apply consistently to chat, sidebar, composer, auth, library,
Studio, settings, dialogs, tables, code blocks and existing PC-control screens.
Preserve semantic warning/error/success colors, readable disabled states and focus
indicators. Use consistent spacing, rounded corners, subtle borders and shadows.

Support responsive browser, Android and desktop layouts. Do not implement new
features just because they appear in the mockup. Do not change credentials,
authentication, routing, billing, generation lifecycle or PC permissions.

Test selection, persistence, system behavior and preference migration. Run formatting,
analysis, relevant Flutter tests and a web build on the pinned SDK. Report unrun
checks plainly. Summarize the files changed and validation; do not deploy to AWS
automatically or overwrite its custom frontend.
