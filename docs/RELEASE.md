# Release process and checklist

## Versioning

* App version: `version:` in `apps/dhanz_flutter/pubspec.yaml` (`MAJOR.MINOR.PATCH+BUILD`; the
  build number must increase for every store upload).
* Backend/API version: `backend/app/main.py` (`FastAPI(version=...)`).
* Tag releases `vMAJOR.MINOR.PATCH` (pre-releases: `v0.2.0-beta.1`). Pushing a tag runs
  `.github/workflows/release.yml`, which builds Android, Windows and iOS and attaches the
  artifacts to a GitHub Release.

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

Without signing secrets the workflow still succeeds, producing a debug-signed APK/AAB (not
accepted by Google Play) and an unsigned iOS `Runner.app` zip (not installable on devices).

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
- [ ] `APP_ENV=production`, strong `JWT_SECRET`, PostgreSQL (not SQLite)
- [ ] Provider keys set in the secret manager; `GET /api/v1/health/ready` lists them
- [ ] Migrations applied (`alembic upgrade head`) and a database backup taken first
- [ ] TLS terminated; `CORS_ORIGINS` and `FORWARDED_ALLOW_IPS` set correctly
- [ ] `python tests/e2e/smoke_test.py --base-url https://api.example.com` passes

**Android**
- [ ] Release keystore used (not debug); `versionCode` increased
- [ ] Tested on a physical device and the minimum supported Android version
- [ ] Play Console: privacy policy URL, Data safety form (account data, conversations sent to AI providers), content rating, target API level requirement met

**iOS**
- [ ] Bundle ID, Team and provisioning profile correct; build number increased
- [ ] App Privacy details in App Store Connect; privacy policy URL; account deletion available in-app (it is: Settings → Delete account)
- [ ] TestFlight build smoke-tested on iPhone and iPad

**Windows**
- [ ] Installer installs, launches, creates Start Menu entry/desktop shortcut and uninstalls cleanly on Windows 10 and 11
- [ ] (Recommended) installer and exe signed with an Authenticode certificate

**After release**
- [ ] GitHub Release published with artifacts and notes
- [ ] Monitor error logs and provider usage/cost for the first 48 hours
