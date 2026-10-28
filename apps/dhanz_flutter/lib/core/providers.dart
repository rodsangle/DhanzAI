import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api/api_client.dart';
import 'config.dart';
import 'storage/secure_store.dart';

/// Overridden in tests with [MemorySecureStore].
final secureStoreProvider = Provider<SecureStore>((ref) => FlutterSecureStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient(store: ref.watch(secureStoreProvider), baseUrl: AppConfig.defaultApiUrl);
  ref.onDispose(client.close);
  return client;
});

class ThemeModeController extends Notifier<ThemeMode> {
  @override
  ThemeMode build() {
    _load();
    return ThemeMode.dark;
  }

  Future<void> _load() async {
    final saved = await ref.read(secureStoreProvider).read(StoreKeys.themeMode);
    final mode = ThemeMode.values.asNameMap()[saved];
    if (mode != null && ref.mounted) state = mode;
  }

  Future<void> set(ThemeMode mode) async {
    state = mode;
    await ref.read(secureStoreProvider).write(StoreKeys.themeMode, mode.name);
  }
}

final themeModeProvider = NotifierProvider<ThemeModeController, ThemeMode>(ThemeModeController.new);
