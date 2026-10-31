# Windows local AI

Open **Use local AI on this PC** from Welcome or the offline/loading screen.
Signed-in users can open **Settings → Local / Cloud / Hybrid chat**.

- **Local** sends text only to `http://127.0.0.1:11434/v1/chat/completions`.
  Select `qwen3:8b` (lighter) or `qwen3:14b`, then **Test connection**.
  No account or internet is required. Connection testing checks `/v1/models`
  and confirms the selected model exists.
- **Cloud** uses the existing FastAPI client, account and configured server URL.
- **Hybrid** tries local first and falls back to FastAPI if local fails before
  any text arrives. Selecting Hybrid authorizes sending the conversation history
  to that server. It requires a signed-in account for fallback. A partial local
  answer is kept on failure and never triggers automatic cloud fallback.

This workspace has session-only history, cleared when leaving the screen.
Cloud requests include the current transcript and create temporary server chats
(subject to the existing server retention policy). Local chat does not upload
files, use server memory, research, or run tools. The original main cloud chat
retains these features and saved conversation history.

## Ollama setup

Install/start Ollama on Windows. If the models are not already installed:

```powershell
ollama pull qwen3:8b
ollama pull qwen3:14b
Invoke-RestMethod http://127.0.0.1:11434/v1/models
```

Keep Ollama's default loopback binding. If `OLLAMA_HOST` was previously changed,
set it to `127.0.0.1:11434` in your Windows user environment variables and restart
Ollama. No firewall opening, port forwarding, public tunnel, API key, or cloud
credential changes are needed. Never bind Ollama to `0.0.0.0` for this app.

If a connection test fails, start Ollama, check the model list above, and retry.
If the 14B model is slow or times out, try 8B. **Stop** closes the local request;
partial text remains visible. Interrupted streams display an error. A failure
before any output restores the prompt for retry. Cloud failures require restoring
the server/internet connection; Local remains usable while offline.

## Build and install

1. Install Flutter stable compatible with Dart 3.13.7 (validated with Flutter
   3.47.9). Use an SDK path without spaces, such as `C:\src\flutter`.
2. Install Visual Studio with **Desktop development with C++**, its Windows SDK,
   MSVC and CMake defaults. Enable **Developer Mode** in Windows Settings so
   Flutter can create plugin symlinks.
3. From `apps/dhanz_flutter`, run:

```powershell
flutter doctor -v
flutter pub get
flutter analyze
flutter test
dart run tool/ollama_smoke.dart  # optional; requires running Ollama and both models
flutter build windows --release
```

Preserve your usual `--dart-define=DHANZ_API_URL=...` build argument if you bake
in a cloud URL. No keys belong in the build arguments. The existing saved server
URL setting also remains available. The default FastAPI URL is localhost:8000.

Copy the **entire** `build/windows/x64/runner/Release` directory to the target PC
and launch `dhanz_ai.exe`; keep its DLLs and `data` directory alongside it.
Ollama and the models are installed separately on each PC. This is a portable
release directory, not an installer. Existing repository release packaging can
also be used after a successful build.

## Verification in this workspace

All 56 Flutter tests passed, static analysis was clean, and live connection plus
streamed-content smoke checks passed for both `qwen3:8b` and `qwen3:14b`.

The Windows release command was attempted but stopped because Developer Mode
(plugin symlinks) is disabled. `flutter doctor -v` also reports Visual Studio
missing. No Windows executable was produced. Install those prerequisites, then
rerun the commands above.

References: [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility),
[Ollama configuration](https://docs.ollama.com/faq),
[Flutter Windows prerequisites](https://docs.flutter.dev/platform-integration/windows/setup).
