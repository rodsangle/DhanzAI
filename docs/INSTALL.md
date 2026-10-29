# Installation and running

DHANZ AI has two parts: the **backend** (FastAPI + PostgreSQL, holds the AI provider keys) and
the **app** (Flutter, installed on each device). The apps need a reachable backend; real-time
answers from cloud models always need an internet connection.

## 1. Backend

### Option A — Docker (recommended)

Prerequisites: Docker with Compose v2.

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, JWT_SECRET, APP_ENV=production and at least one of
# OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY / OLLAMA_BASE_URL.
docker compose up -d --build
curl http://localhost:8000/api/v1/health/ready      # {"status":"ok","database":true,"providers":[...]}
```

Migrations run automatically on container start. For internet-facing deployments put a TLS
reverse proxy (Caddy, nginx, a cloud load balancer) in front of port 8000 and point the apps at
`https://your-domain`.

### Option B — Local Python (development)

Prerequisites: Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r backend/requirements-dev.txt
cd backend
cp ../.env.example .env        # dev defaults use SQLite (./dhanz.db) when DATABASE_URL is unset
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs for the interactive API.

### Web research and the knowledge library (optional)

Set one search provider in `.env` and restart the API:

```bash
SEARCH_PROVIDER=brave        # or tavily / searxng
BRAVE_API_KEY=...            # https://brave.com/search/api/
# TAVILY_API_KEY=...         # https://tavily.com
# SEARXNG_URL=http://searxng:8080   # self-hosted, JSON format enabled
```

For semantic search in the knowledge library also set `EMBEDDING_PROVIDER=openai` (or
`gemini` / `ollama`, using that provider's key/URL above). Without it, keyword search is used.
`GET /api/v1/models` reports `features.web_search` / `features.semantic_search`.

The API reads public web pages itself, so it needs outbound HTTPS access to the internet.

### Files, voice and malware scanning (optional)

```bash
MAX_UPLOAD_MB=20
STT_PROVIDER=openai                 # voice assistant speech-to-text; uses OPENAI_API_KEY by default
# STT_BASE_URL=http://whisper:8000/v1   # or a self-hosted OpenAI-compatible Whisper server
CLAMAV_HOST=clamav                  # with: docker compose --profile scan up -d
```

Uploaded files are stored in the `uploads` Docker volume. Text-to-speech uses the voices installed
on each device. The apps ask for microphone permission the first time the Voice screen is used.

### Push notifications and app updates (optional)

* **Push** ("your answer is ready" on phones): set `FCM_SERVICE_ACCOUNT_FILE` (Android) and/or the
  `APNS_*` variables (iOS) from `.env.example`. The apps also need Firebase / the Push capability;
  step-by-step in [RELEASE.md](RELEASE.md#push-notifications). Without them everything works,
  answers simply are not announced.
* **Updates**: copy `latest.json` from a GitHub release to the server and set `UPDATE_MANIFEST_FILE`.

### Production server

For a server reachable from the internet (HTTPS, backups, monitoring) use `deploy/` and follow
[DEPLOY.md](DEPLOY.md). The first account registered on a new server becomes its administrator.

### Using local models (Ollama)

Install [Ollama](https://ollama.com), run `ollama pull llama3.1`, then set
`OLLAMA_BASE_URL=http://localhost:11434` (or `http://host.docker.internal:11434` from Docker) and
`OLLAMA_MODELS=llama3.1`. Choose the *Local first* routing policy in the app's settings.

## 2. App — development run

Prerequisites: [Flutter](https://docs.flutter.dev/get-started/install) 3.47+ (stable).

```bash
cd apps/dhanz_flutter
flutter pub get
flutter run -d windows                                   # Windows desktop
flutter run -d <android-device-id>                       # Android (emulator reaches host via 10.0.2.2)
flutter run -d <ios-simulator-id>                        # iOS (macOS + Xcode)
flutter run --dart-define=DHANZ_API_URL=https://api.example.com   # point at a deployed backend
```

The server URL can also be changed on the sign-in screen (*Server*).

## 3. App — installable builds

Always pass your production backend: `--dart-define=DHANZ_API_URL=https://api.example.com`.
The GitHub **Release builds** workflow produces all of these automatically (see
[RELEASE.md](RELEASE.md)).

### Windows 10 / 11

On a Windows machine with Visual Studio 2022 ("Desktop development with C++"):

```powershell
cd apps\dhanz_flutter
flutter build windows --release --dart-define=DHANZ_API_URL=https://api.example.com
# Installer (Start Menu entry, optional desktop shortcut, uninstaller):
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=0.1.0 ..\..\scripts\windows\dhanz_ai.iss
```

Run `dist\dhanz-ai-0.1.0-windows-setup.exe`. Uninstall from *Settings → Apps*. Unsigned
installers trigger a SmartScreen warning; sign with an Authenticode certificate for distribution.

The Windows app has a tray icon (Settings → *Keep running in the system tray*), shows a desktop
notification when an answer finishes while the window is in the background, accepts files dragged
onto the chat, and offers new versions from the update banner.

### Android

```bash
flutter build apk --release --dart-define=DHANZ_API_URL=https://api.example.com        # direct install
flutter build appbundle --release --dart-define=DHANZ_API_URL=https://api.example.com  # Google Play
```

* APK: `build/app/outputs/flutter-apk/app-release.apk` → copy to the phone and allow
  "Install unknown apps" for your file manager, or `adb install app-release.apk`.
* AAB: upload to Google Play Console. Play requires a release keystore (see RELEASE.md); builds
  without one are debug-signed and only suitable for testing.

### iPhone / iPad (requires macOS, Xcode and an Apple Developer account)

Apps can only be installed on iOS devices when signed. Public distribution requires the App
Store (or Apple-approved alternatives such as TestFlight / enterprise programs).

1. `open apps/dhanz_flutter/ios/Runner.xcworkspace` in Xcode.
2. *Runner → Signing & Capabilities*: select your Team; set a unique Bundle Identifier
   (default `ai.dhanz.dhanzAi`).
3. Build an archive:
   ```bash
   cd apps/dhanz_flutter
   flutter build ipa --release --dart-define=DHANZ_API_URL=https://api.example.com
   ```
   Output: `build/ios/ipa/*.ipa`, plus `build/ios/archive/Runner.xcarchive`.
4. Distribute: open the archive in Xcode *Organizer* → *Distribute App* → App Store Connect
   (TestFlight / App Store) or Ad Hoc (registered devices only), or upload with the Transporter app.

### macOS (preview)

```bash
flutter build macos --release --dart-define=DHANZ_API_URL=https://api.example.com
```

Signing and notarization are required for distribution outside your own machine.
