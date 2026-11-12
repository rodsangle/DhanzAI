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

/// The theme the user picked (Settings → Appearance), stored on the device.
///
/// Older versions stored only light/dark/system under `theme_mode`; that is converted on first
/// load (light → Arctic Light, dark → Midnight Gold, system → Follow system) and saved under
/// `app_theme`. The old key is kept up to date so an older build on the same device still works.
class ThemePreferenceController extends Notifier<ThemePreference> {
  @override
  ThemePreference build() {
    _load();
    return ThemePreference.midnightGold;
  }

  Future<void> _load() async {
    final store = ref.read(secureStoreProvider);
    try {
      final stored = await store.read(StoreKeys.appTheme);
      final preference = ThemePreference.fromStored(
        stored: stored ?? await store.read(StoreKeys.themeStyle),
        legacy: await store.read(StoreKeys.themeMode),
      );
      if (stored != preference.name) await store.write(StoreKeys.appTheme, preference.name); // migrate once
      if (ref.mounted) state = preference;
    } catch (_) {
      // Storage unavailable (e.g. blocked browser storage): keep the default theme.
    }
  }

  Future<void> set(ThemePreference preference) async {
    state = preference;
    final store = ref.read(secureStoreProvider);
    await store.write(StoreKeys.appTheme, preference.name);
    await store.write(StoreKeys.themeMode, preference.legacyName);
  }
}

final themePreferenceProvider = NotifierProvider<ThemePreferenceController, ThemePreference>(
  ThemePreferenceController.new,
);
