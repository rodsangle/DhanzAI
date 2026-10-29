import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../core/storage/secure_store.dart';
import '../../models/models.dart';

/// Signed-in user, or null when signed out. Errors mean the server could not be reached.
class AuthController extends AsyncNotifier<User?> {
  ApiClient get _api => ref.read(apiClientProvider);

  @override
  Future<User?> build() async {
    final api = ref.watch(apiClientProvider);
    api.onSessionExpired = () {
      if (ref.mounted) state = const AsyncData(null);
    };
    final savedUrl = await ref.read(secureStoreProvider).read(StoreKeys.apiUrl);
    if (savedUrl != null && savedUrl.isNotEmpty) api.baseUrl = savedUrl;
    if (!await api.hasSession()) return null;
    try {
      return await api.me();
    } on ApiException catch (e) {
      if (e.isUnauthorized) {
        await api.clearTokens();
        return null;
      }
      rethrow;
    }
  }

  Future<void> setServerUrl(String url) async {
    final trimmed = url.trim().replaceAll(RegExp(r'/+$'), '');
    _api.baseUrl = trimmed;
    await ref.read(secureStoreProvider).write(StoreKeys.apiUrl, trimmed);
  }

  Future<void> login(String email, String password) async {
    final tokens = await _api.login(email.trim(), password);
    state = AsyncData(tokens.user);
  }

  Future<void> register(String email, String password, String displayName) async {
    final tokens = await _api.register(email.trim(), password, displayName.trim());
    state = AsyncData(tokens.user);
  }

  void updateUser(User user) => state = AsyncData(user);

  Future<void> logout() async {
    // Stop "answer ready" notifications to this phone for the account being signed out.
    final store = ref.read(secureStoreProvider);
    final pushToken = await store.read(StoreKeys.pushToken);
    if (pushToken != null) {
      try {
        await _api.unregisterDevice(pushToken);
      } on ApiException {
        // signing out must still work offline
      }
      await store.write(StoreKeys.pushToken, null);
    }
    await _api.logout();
    state = const AsyncData(null);
  }

  Future<void> deleteAccount(String password) async {
    await _api.deleteAccount(password);
    state = const AsyncData(null);
  }
}

final authControllerProvider = AsyncNotifierProvider<AuthController, User?>(AuthController.new);
