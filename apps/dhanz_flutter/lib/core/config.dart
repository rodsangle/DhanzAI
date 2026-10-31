import 'package:flutter/foundation.dart';

/// Build-time configuration. Override with:
///   flutter run --dart-define=DHANZ_API_URL=https://api.example.com
class AppConfig {
  static const appName = 'DHANZ AI';
  static const assistantName = 'Dhanz';
  static const tagline = 'Your World. Your Knowledge. Your AI.';
  static const greeting = "Hello! I'm Dhanz, your personal AI assistant. How can I help you today?";

  static const _apiUrlOverride = String.fromEnvironment('DHANZ_API_URL');
  static const tailscaleServerUrl = 'https://danterog.tail8bd40a.ts.net';

  /// Upgrade the old development addresses while preserving custom servers.
  static String resolveSavedApiUrl(String? savedUrl) {
    final url = savedUrl?.trim().replaceAll(RegExp(r'/+$'), '');
    if (url == null || url.isEmpty) return defaultApiUrl;
    if (kReleaseMode &&
        const {'http://localhost:8000', 'http://127.0.0.1:8000', 'http://10.0.2.2:8000'}.contains(url)) {
      return defaultApiUrl;
    }
    return url;
  }

  /// Default backend URL. The Android emulator reaches the host machine via 10.0.2.2.
  static String get defaultApiUrl {
    if (_apiUrlOverride.isNotEmpty) return _apiUrlOverride;
    if (kReleaseMode) return tailscaleServerUrl;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return 'http://localhost:8000';
  }

  static const apiPrefix = '/api/v1';
}
