# Chat file preview panel (web 0.10.1, build 31)

Press **Preview** beside an uploaded or generated file to open its content in a
panel on the right of chat. The panel starts closed and does not open when files
arrive or replies finish. The chat toolbar also has a Preview toggle; it opens
the previously selected file or an empty prompt to select a file.

On wide layouts, drag the divider on the panel's left edge to change its width.
The expand button fills the available chat area; press restore to return to the
split layout. Close with the upper-right X, toolbar toggle, or Escape. A new chat
or conversation switch clears the previous file selection. Phone layouts show
the panel over chat with the same close and expand controls.

Worksheet tabs, selectable content, loading/retry states and the real Download
button use the existing authenticated preview API. Previewing never changes the
workbook. Office layout may differ, and formulas are shown without calculation.
Uploads, coding, sharing, feedback, search and the existing server tools remain.

## Install

Use Settings > Update if web updates are already configured. Otherwise download
`deploy/updaters/install_chat_preview.py` from the published source commit, then
run `python3 ~/install_chat_preview.py --apply` in AWS. This installs the latest
checked web-channel build without rebuilding Flutter or restarting the API. The
installer validates the current served release, manifest, package checksum and
archive, backs up the static browser assets, and prints its rollback path.

Refresh Edge with Ctrl+F5. For an older Android PWA, open
`https://dhanzai.com/app/update.html`, refresh the installed app, then close and
reopen it. Browser Settings should show 0.10.1 build 31 (or a newer checked build).
No native APK is produced: Android uses the installed web app.

## Checks

The Flutter widget tests cover initially closed behavior, explicit open, close,
Escape, drag resizing, expand/restore state, phone constraints, file changes and
selection clearing. The release workflow runs full analysis/tests and compiles
the web client before publishing its ZIP and update-channel manifest.
