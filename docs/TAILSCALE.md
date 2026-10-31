# DHANZ AI over Tailscale

This personal release uses `https://danterog.tail8bd40a.ts.net` by default.
The address stays the same when the laptop changes Wi-Fi. Both the laptop and
the client device must be connected to the same Tailscale network.

Release upgrades replace saved `localhost:8000`, `127.0.0.1:8000` and Android
emulator `10.0.2.2:8000` HTTP addresses with the release default. Custom server
addresses are preserved. Debug builds retain their local development defaults.
Use `--dart-define=DHANZ_API_URL=https://your-server` to override the release address.

## Laptop

Keep the laptop awake with an internet connection. Run the backend using
`scripts/start-web-api.ps1` (it listens on `127.0.0.1:8000`). Tailscale Serve
forwards private HTTPS traffic to this local service. In an administrator
PowerShell window, if you need to restore the configuration:

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' up
& 'C:\Program Files\Tailscale\tailscale.exe' serve --bg http://127.0.0.1:8000
& 'C:\Program Files\Tailscale\tailscale.exe' serve status
```

Enable Serve/HTTPS in the Tailscale admin page if prompted. Do not enable
Funnel for this private setup. Serve's background configuration persists;
the backend must also be running after a reboot.

## Phone

Connect the Tailscale app, then open the DHANZ AI app and sign in with your
DHANZ AI account. Older apps can use the same URL in the sign-in screen's
Server field. Do not append `/api/v1` or `:8000` to the server URL.

For a connection check, open
`https://danterog.tail8bd40a.ts.net/api/v1/health/ready` in the phone browser.
It should return JSON with `"status":"ok"`. A host lookup error means the
device could not resolve the Tailscale hostname; check Tailscale connectivity
and its DNS settings before changing the app's server URL.

## Build

From `apps/dhanz_flutter`, run `flutter build windows --release` or
`flutter build apk --release`. Android builds require an Android SDK and
the original release signing key to upgrade an existing installed APK.
Package Windows with `.tools/inno/ISCC.exe scripts/windows/dhanz_ai.iss`
from the repository root. Version 0.8.1 uses build number 9.
