import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_sign_in/google_sign_in.dart';
import 'package:sign_in_with_apple/sign_in_with_apple.dart';

import '../../models/models.dart';

/// What Google or Apple handed back: the ID token the server verifies.
class SocialCredential {
  const SocialCredential({required this.idToken, this.nonce, this.displayName});

  final String idToken;

  /// The raw nonce sent with the request (the server checks the token carries it).
  final String? nonce;

  /// Apple shares the name only with the app, on the first sign-in.
  final String? displayName;
}

/// Runs the platform's own "Sign in with Google / Apple" UI.
abstract class SocialSignIn {
  /// Whether [provider] ("google" or "apple") can be offered on this device with this server.
  bool supports(String provider, AuthOptions options);

  /// Null when the user cancelled.
  Future<SocialCredential?> signIn(String provider, AuthOptions options);
}

/// The iOS OAuth client ID for Google Sign-In, from `--dart-define=GOOGLE_IOS_CLIENT_ID=...`.
/// iOS also needs its reversed form as a URL scheme in Info.plist (see docs/RELEASE.md).
const _googleIosClientId = String.fromEnvironment('GOOGLE_IOS_CLIENT_ID');

class SocialSignInException implements Exception {
  const SocialSignInException(this.message);

  final String message;

  @override
  String toString() => message;
}

String _randomNonce() {
  final random = Random.secure();
  return base64Url.encode(List<int>.generate(32, (_) => random.nextInt(256))).replaceAll('=', '');
}

class PluginSocialSignIn implements SocialSignIn {
  bool _googleReady = false;

  @override
  bool supports(String provider, AuthOptions options) {
    if (kIsWeb) return false; // web needs the providers' own buttons: not wired up yet
    return switch (provider) {
      'google' =>
        options.googleClientId != null &&
            (defaultTargetPlatform == TargetPlatform.android ||
                (defaultTargetPlatform == TargetPlatform.iOS && _googleIosClientId.isNotEmpty)),
      'apple' => options.appleSignIn && defaultTargetPlatform == TargetPlatform.iOS,
      _ => false,
    };
  }

  @override
  Future<SocialCredential?> signIn(String provider, AuthOptions options) =>
      provider == 'google' ? _google(options) : _apple();

  Future<SocialCredential?> _google(AuthOptions options) async {
    final google = GoogleSignIn.instance;
    try {
      if (!_googleReady) {
        await google.initialize(
          clientId: _googleIosClientId.isEmpty ? null : _googleIosClientId,
          serverClientId: options.googleClientId,
        );
        _googleReady = true;
      }
      final account = await google.authenticate(scopeHint: const ['email']);
      final token = account.authentication.idToken;
      if (token == null) throw const SocialSignInException('Google did not return a sign-in token.');
      return SocialCredential(idToken: token);
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) return null;
      throw SocialSignInException(
        e.code == GoogleSignInExceptionCode.clientConfigurationError
            ? 'Google sign-in is not set up correctly for this app.'
            : 'Google sign-in failed. Please try again.',
      );
    }
  }

  Future<SocialCredential?> _apple() async {
    final nonce = _randomNonce();
    try {
      final credential = await SignInWithApple.getAppleIDCredential(
        scopes: const [AppleIDAuthorizationScopes.email, AppleIDAuthorizationScopes.fullName],
        nonce: sha256.convert(utf8.encode(nonce)).toString(),
      );
      final token = credential.identityToken;
      if (token == null) throw const SocialSignInException('Apple did not return a sign-in token.');
      final name = [credential.givenName, credential.familyName].whereType<String>().join(' ').trim();
      return SocialCredential(idToken: token, nonce: nonce, displayName: name.isEmpty ? null : name);
    } on SignInWithAppleAuthorizationException catch (e) {
      if (e.code == AuthorizationErrorCode.canceled) return null;
      throw const SocialSignInException('Sign in with Apple failed. Please try again.');
    }
  }
}

final socialSignInProvider = Provider<SocialSignIn>((ref) => PluginSocialSignIn());
