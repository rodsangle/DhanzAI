# Release process and checklist

## Versioning

* App version: `version:` in `apps/dhanz_flutter/pubspec.yaml` (`MAJOR.MINOR.PATCH+BUILD`; the
  build number must increase for every store upload).
* Backend/API version: `backend/app/main.py` (`FastAPI(version=...)`).
* Tag releases `vMAJOR.MINOR.PATCH` (pre-releases: `v0.2.0-beta.1`). Pushing a tag runs
  `.github/workflows/release.yml`, which builds Android, Windows, iOS and macOS, attaches the
  artifacts to a GitHub Release, and publishes the server image `ghcr.io/<owner>/<repo>/api:<version>`
  (lower-case) with build provenance and an SBOM. Tagged builds get their version from the tag (`v0.4.0` → `0.4.0`,
  build number = workflow run number), so the in-app update check compares real versions.

## CI configuration (GitHub → Settings → Secrets and variables → Actions)

| Name | Type | Purpose |
|---|---|---|
| `DHANZ_API_URL` | variable | Backend URL compiled into the apps (`https://…`) |
| `ANDROID_KEYSTORE_BASE64` | secret | `base64 -w0 release.jks` |
| `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD` | secrets | Keystore credentials |
| `IOS_CERTIFICATE_P12_BASE64`, `IOS_CERTIFICATE_PASSWORD` | secrets | Apple Distribution certificate |
| `IOS_PROVISIONING_PROFILE_BASE64` | secret | App Store or Ad Hoc provisioning profile |
| `IOS_EXPORT_OPTIONS_PLIST_BASE64` | secret | `ExportOptions.plist` matching the profile (method, teamID, provisioningProfiles) |
| `IOS_KEYCHAIN_PASSWORD` | secret | Any random string for the temporary CI keychain |
| `WINDOWS_CERT_PFX_BASE64`, `WINDOWS_CERT_PASSWORD` | secrets | Authenticode code-signing certificate (`.pfx`, base64) for `dhanz_ai.exe` and the installer |
| `DHANZ_GOOGLE_SERVICES_JSON` | secret | Contents of `google-services.json` from your Firebase project; enables Android push |

Android release builds require the existing signing keystore. The workflow fails if it is
missing instead of publishing an APK signed with a new runner's debug key, which cannot
update existing installations. Without Apple signing secrets, the iOS output remains an
unsigned `Runner.app` zip for build verification, not an installable device update.

## Updating the existing application

Do not uninstall before updating. Keep application identities stable:

* Windows: run `dhanz-ai-<version>-windows-setup.exe`. Its stable Inno AppId reuses the
  previous installation folder, scope, tasks and Start Menu group. The default is the
  per-user `%LOCALAPPDATA%\Programs\DHANZ AI` directory. Manually copied portable apps
  must be updated by selecting their existing directory. AppData settings and backend
  databases are outside the packaged application files and are not deleted by setup.
* Android: retain `ai.dhanz.dhanz_ai`, sign with the installed app's existing key (or use
  its Play App Signing distribution), and increase `versionCode`. Install the APK over
  the old app or publish an update to its existing Play Store listing. Never resolve a
  signature mismatch by telling users to uninstall: obtain the matching key instead.
* iOS: retain `ai.dhanz.dhanzAi`, the existing Apple team and App Store Connect app;
  increase the build number and distribute through the same App Store/TestFlight app.
* macOS: retain the bundle ID and signing identity; replace the existing app bundle in
  Applications. Do not rename each release or create a second bundle beside the old one.
* Web: deploy the new build to the same site URL; users reload the existing site.

The installer accepts `/NOLAUNCH` for packaging verification. The in-app Windows updater
uses the setup EXE and its SHA-256 from `latest.json`, not a portable ZIP. Publishing the
manifest on GitHub does not configure the backend: copy it to `UPDATE_MANIFEST_FILE`.

References: [Inno upgrade identity](https://jrsoftware.org/ishelp/topic_setup_appid.htm),
[Android signing](https://developer.android.com/studio/publish/app-signing),
[Android versioning](https://developer.android.com/studio/publish/versioning).

Without `WINDOWS_CERT_PFX_BASE64` the Windows build is unsigned (SmartScreen warns on first run);
without `DHANZ_GOOGLE_SERVICES_JSON` the Android app has no push notifications.

## In-app updates

Each tagged release also publishes `latest.json`:

```json
{"version": "0.4.0", "notes": "DHANZ AI v0.4.0",
 "platforms": {"windows": {"url": "https://github.com/…/dhanz-ai-0.4.0-windows-setup.exe", "sha256": "…"},
               "android": {"url": "https://github.com/…/dhanz-ai-v0.4.0.apk", "sha256": "…"}}}
```

Copy it to the server and set `UPDATE_MANIFEST_FILE` to its path (in Docker, put it in the
`/srv/data` volume). Add `"minimum_version": "0.3.0"` to force older apps to update (the banner
then cannot be dismissed). Apps call `GET /api/v1/app/updates`:

* **Windows** downloads the installer, checks the SHA-256, runs it with `/SILENT /CLOSEAPPLICATIONS`
  and the new version starts automatically.
* **Android** opens the APK link. Remove the `android` entry if you distribute through Google Play.
* **iOS / macOS**: iOS updates come from the App Store/TestFlight (no entry is generated); macOS
  opens the download page.

## Push notifications

The server notifies a phone when an answer finishes while the app is not open.

**Android (Firebase Cloud Messaging)**
1. Create a Firebase project, add an Android app with package `ai.dhanz.dhanz_ai`, download
   `google-services.json` and put it in `apps/dhanz_flutter/android/app/` (git-ignored) or in the
   `DHANZ_GOOGLE_SERVICES_JSON` secret. The Gradle build applies the Google Services plugin only
   when this file exists.
2. Firebase console → Project settings → Service accounts → *Generate new private key*. Give the
   JSON to the server as `FCM_SERVICE_ACCOUNT_FILE` (or `FCM_SERVICE_ACCOUNT_JSON`).

**iOS (Apple Push Notification service)**
1. In Xcode open `ios/Runner.xcworkspace` → Runner target → *Signing & Capabilities* → add
   **Push Notifications** (this creates the `aps-environment` entitlement; the provisioning profile
   must include it).
2. developer.apple.com → Keys → create a key with *Apple Push Notifications service*. Configure the
   server with `APNS_TEAM_ID`, `APNS_KEY_ID`, `APNS_PRIVATE_KEY_FILE` (the `.p8`) and
   `APNS_BUNDLE_ID=ai.dhanz.dhanzAi`. Use `APNS_USE_SANDBOX=true` for builds installed from Xcode.

`GET /api/v1/models` reports `features.push_notifications`; the app only asks for notification
permission when the server has push configured.

### Creating the Android upload keystore

```bash
keytool -genkey -v -keystore release.jks -keyalg RSA -keysize 4096 -validity 10000 -alias dhanz
```

Keep `release.jks` and its passwords outside the repository (back them up — losing the key
means you cannot update the app unless you use Play App Signing's key-reset process). For
local builds create `apps/dhanz_flutter/android/key.properties` (git-ignored):

```properties
storeFile=/absolute/path/to/release.jks
storePassword=...
keyAlias=dhanz
keyPassword=...
```

## Release checklist

**Code and quality**
- [ ] CI green on the release commit (backend, Postgres e2e, Docker, Flutter)
- [ ] `docs/ROADMAP.md` status table updated; no unfinished feature exposed in the UI
- [ ] Version and build number bumped in `pubspec.yaml`; changelog/release notes drafted

**Backend**
- [ ] Server image published (`server-image` job) and `deploy/` updated per DEPLOY.md
- [ ] `APP_ENV=production`, strong `JWT_SECRET`, PostgreSQL (not SQLite), `REDIS_URL`, SMTP for password reset
- [ ] Backups running and a restore tested; `/metrics` scraped and alerts set
- [ ] CI `dependency-audit` and CodeQL clean
- [ ] Provider keys set in the secret manager; `GET /api/v1/health/ready` lists them
- [ ] Migrations applied (`alembic upgrade head`) and a database backup taken first
- [ ] TLS terminated; `CORS_ORIGINS` and `FORWARDED_ALLOW_IPS` set correctly
- [ ] `python tests/e2e/smoke_test.py --base-url https://api.example.com` passes

**Android**
- [ ] Release keystore used (not debug); `versionCode` increased
- [ ] Tested on a physical device and the minimum supported Android version
- [ ] Push: leave the app during a long answer → notification arrives → tapping it opens the answer
- [ ] Play Console: privacy policy URL, Data safety form (account data, conversations sent to AI providers), content rating, target API level requirement met

**iOS**
- [ ] Bundle ID, Team and provisioning profile correct; build number increased
- [ ] App Privacy details in App Store Connect; privacy policy URL; account deletion available in-app (it is: Settings → Delete account)
- [ ] TestFlight build smoke-tested on iPhone and iPad
- [ ] Push capability enabled; notification received with the production APNs environment

**Windows**
- [ ] Installer installs, launches, creates Start Menu entry/desktop shortcut and uninstalls cleanly on Windows 10 and 11
- [ ] (Recommended) installer and exe signed with an Authenticode certificate
- [ ] Tray icon, minimize to tray, desktop notification and drag-and-drop checked
- [ ] Update from the previous release through the in-app banner works (installer verified, app restarts)

**Updates**
- [ ] `latest.json` from the release copied to the server's `UPDATE_MANIFEST_FILE`

**After release**
- [ ] GitHub Release published with artifacts and notes
- [ ] Monitor error logs and provider usage/cost for the first 48 hours
