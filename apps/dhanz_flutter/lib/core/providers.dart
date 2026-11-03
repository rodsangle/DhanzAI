import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/api_client.dart';
import 'config.dart';
import 'storage/secure_store.dart';
import 'theme.dart';

/// Overridden in tests with [MemorySecureStore].
final secureStoreProvider = Provider<SecureStore>((ref) => FlutterSecureStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(store: ref.watch(secureStoreProvider), baseUrl: AppConfig.defaultApiUrl);
  ref.onDispose(client.close);
  return client;
});

class ThemeModeController extends Notifier<ThemeMode> {
  bool _edited = false;
  @override
  ThemeMode build() {
    _load();
    return ThemeMode.dark;
  }

  Future<void> _load() async {
    try {
      final saved = await ref.read(secureStoreProvider).read(StoreKeys.themeMode);
      final mode = ThemeMode.values.asNameMap()[saved];
      if (mode != null && ref.mounted && !_edited) state = mode;
    } catch (_) {
      // A temporarily unavailable preference store must not prevent app startup.
    }
  }

  Future<void> set(ThemeMode mode) async {
    _edited = true;
    state = mode;
    await ref.read(secureStoreProvider).write(StoreKeys.themeMode, mode.name);
  }
}

final themeModeProvider = NotifierProvider<ThemeModeController, ThemeMode>(ThemeModeController.new);

class ThemeStyleController extends Notifier<DhanzThemeStyle> {
  bool _edited = false;
  Future<void> _write = Future<void>.value();

  @override
  DhanzThemeStyle build() {
    _load();
    return DhanzThemeStyle.original;
  }

  Future<void> _load() async {
    try {
      final saved = await ref.read(secureStoreProvider).read(StoreKeys.themeStyle);
      final style = DhanzThemeStyle.values.asNameMap()[saved];
      if (ref.mounted && !_edited && style != null) state = style;
    } catch (_) {
      // Keep the original appearance when storage is unavailable.
    }
  }

  Future<void> set(DhanzThemeStyle style) {
    _edited = true;
    state = style;
    final store = ref.read(secureStoreProvider);
    // Serialize fast clicks so the final selection also wins in persistent storage.
    _write = _write.then(
      (_) => store.write(StoreKeys.themeStyle, style.name),
      onError: (Object _) => store.write(StoreKeys.themeStyle, style.name),
    );
    return _write;
  }
}

final themeStyleProvider = NotifierProvider<ThemeStyleController, DhanzThemeStyle>(ThemeStyleController.new);
