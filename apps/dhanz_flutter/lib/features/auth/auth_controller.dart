import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/platform/social_sign_in.dart';
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
    ref.invalidate(authOptionsProvider);
  }

  /// Signs in; returns an [MfaChallenge] when an authenticator code is still needed.
  Future<MfaChallenge?> login(String email, String password) async => _apply(await _api.login(email.trim(), password));

  /// "Continue with Google / Apple". Returns null when signed in, or when the user cancelled.
  Future<MfaChallenge?> signInWith(String provider, AuthOptions options) async {
    final credential = await ref.read(socialSignInProvider).signIn(provider, options);
    if (credential == null) return null;
    return _apply(
      await _api.oauthSignIn(
        provider,
        credential.idToken,
        nonce: credential.nonce,
        displayName: credential.displayName,
      ),
    );
  }

  Future<void> completeMfa(MfaChallenge challenge, String code) async {
    final tokens = await _api.verifyMfa(challenge, code.trim());
    state = AsyncData(tokens.user);
  }

  MfaChallenge? _apply(Object result) {
    if (result is MfaChallenge) return result;
    state = AsyncData((result as AuthTokens).user);
    return null;
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

  Future<void> deleteAccount({String? password, String? confirmEmail, String? mfaCode}) async {
    await _api.deleteAccount(password: password, confirmEmail: confirmEmail, mfaCode: mfaCode);
    state = const AsyncData(null);
  }
}

final authControllerProvider = AsyncNotifierProvider<AuthController, User?>(AuthController.new);

/// What this server offers on the sign-in screen (Google/Apple, email codes, ...).
/// Falls back to the basics when the server cannot be reached or predates these options.
final authOptionsProvider = FutureProvider<AuthOptions>((ref) async {
  ref.watch(authControllerProvider.select((s) => s.value?.id));
  try {
    return await ref.read(apiClientProvider).authOptions();
  } on Exception {
    return const AuthOptions();
  }
});
