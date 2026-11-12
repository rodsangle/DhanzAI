# Dhanz 0.9.6 reply sharing

Finished replies with text show **Share reply** alongside Copy and Read aloud. Android PWA and supporting browsers open the device share sheet. Only the selected reply text is passed to the share sheet, with the generic title “Dhanz AI reply”. Chat history, credentials, attachment contents and authenticated download links are not added. No public chat page/link is created and no AI request is made.

If sharing is unavailable or fails, a dialog offers selectable reply text and an explicit **Copy reply** action. Clipboard content changes only after that action. Email/download fallbacks are disabled, and dismissing the native sheet does not copy anything or claim delivery. Repeated taps are blocked while the share sheet/dialog is open. Actual share targets depend on the browser, operating system and installed apps.

The compiled browser package preserves the 0.9.5 coding workspace and existing features. `deploy/updaters/install_pwa_sharing.py --apply` accepts the known 0.9.4+22 or 0.9.5+23 client source, requires the previously requested coding backend and updates only the nested `/app/` web assets. It validates the package/checksum, keeps a private backup and prints its rollback command. Sharing adds no backend image change, database migration, API key, hosting service or model charge. Install the prior coding backend first if the helper reports it missing.

The same browser update serves Edge and the Android PWA. Refresh Edge with Ctrl+F5 and reopen the Android app after installing. Native Windows/Android executable packages are not published by this web-only update.
