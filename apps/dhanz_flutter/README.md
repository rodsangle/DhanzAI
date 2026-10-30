# DHANZ AI — Flutter app

One codebase for Windows, Android and iOS (macOS and web scaffolding included).

```bash
flutter pub get
flutter run -d windows --dart-define=DHANZ_API_URL=http://localhost:8000
flutter test
```

* State: Riverpod (`lib/features/*/..._controller.dart`) · Navigation: GoRouter (`lib/router.dart`)
* Backend access: `lib/core/api/api_client.dart` (REST + SSE streaming, automatic token refresh)
* Secure storage: `flutter_secure_storage` (Keychain / Android Keystore / Windows DPAPI)
* Theme and brand: `lib/core/theme.dart`, `lib/widgets/dhanz_logo.dart`; icons are generated
  from `assets/branding` with `dart run flutter_launcher_icons`.

See `../../docs/INSTALL.md` for release builds on each platform.

For direct Windows Ollama chat, Local/Cloud/Hybrid routing, and offline setup,
see [Windows local AI](../../docs/windows-ollama.md).
