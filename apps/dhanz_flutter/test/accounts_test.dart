import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/app_version.dart';
import 'package:dhanz_ai/core/platform/social_sign_in.dart';
import 'package:dhanz_ai/core/platform/updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

/// Stands in for the Google / Apple plugins: hands out a fixed ID token.
class FakeSocialSignIn implements SocialSignIn {
  bool cancel = false;
  final calls = <String>[];

  @override
  bool supports(String provider, AuthOptions options) =>
      provider == 'google' ? options.googleClientId != null : options.appleSignIn;

  @override
  Future<SocialCredential?> signIn(String provider, AuthOptions options) async {
    calls.add(provider);
    if (cancel) return null;
    return const SocialCredential(idToken: FakeBackend.googleToken, nonce: 'n-1', displayName: 'Ada');
  }
}

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;
  late FakeSocialSignIn social;

  List<Override> overrides() => [
    secureStoreProvider.overrideWithValue(store),
    apiClientProvider.overrideWith(
      (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
    ),
    appVersionProvider.overrideWith((ref) async => '0.7.0'),
    updatePlatformProvider.overrideWithValue(null),
    socialSignInProvider.overrideWithValue(social),
  ];

  ApiClient api() => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
    social = FakeSocialSignIn();
  });

  Future<void> signUp() => api().register('ada@example.com', 'correct-horse-9', 'Ada');

  Future<ProviderContainer> pumpApp(WidgetTester tester, String location) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
    container.read(routerProvider).go(location);
    await tester.pumpAndSettle();
    return container;
  }

  testWidgets('sign-in asks for the authenticator code when two-step verification is on', (tester) async {
    await signUp();
    backend.users['ada@example.com']!['mfa_enabled'] = true;
    await store.deleteAll(); // signed out
    await pumpApp(tester, '/login');
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'ada@example.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Password'), 'correct-horse-9');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
    expect(find.text('Two-step verification'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '000000');
    await tester.tap(find.widgetWithText(FilledButton, 'Verify'));
    await tester.pumpAndSettle();
    expect(find.textContaining('not correct'), findsOneWidget);

    await tester.tap(find.text('Lost your phone? Use a recovery code'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), FakeBackend.recoveryCode.toLowerCase());
    await tester.tap(find.widgetWithText(FilledButton, 'Verify'));
    await tester.pumpAndSettle();
    expect(backend.requests, contains('POST /auth/mfa/verify'));
    expect(find.text('Two-step verification'), findsNothing); // in the app now
    expect(await store.read(StoreKeys.refreshToken), isNotNull);
  });

  testWidgets('Continue with Google creates the account; cancelling does nothing', (tester) async {
    backend.authOptions = {
      ...backend.authOptions,
      'google_client_id': 'web-client.apps.googleusercontent.com',
      'apple_sign_in': true,
    };
    final container = await pumpApp(tester, '/register');
    expect(find.text('Continue with Apple'), findsOneWidget);
    expect(find.text('Continue with Google'), findsOneWidget);

    social.cancel = true;
    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();
    expect(backend.oauthBodies, isEmpty);
    expect(container.read(authControllerProvider).value, isNull);

    social.cancel = false;
    await tester.tap(find.text('Continue with Google'));
    await tester.pumpAndSettle();
    expect(backend.oauthBodies.single, {'id_token': FakeBackend.googleToken, 'nonce': 'n-1', 'display_name': 'Ada'});
    final user = container.read(authControllerProvider).value!;
    expect(user.email, 'ada@gmail.com');
    expect(user.hasPassword, isFalse);
  });

  testWidgets('no Google/Apple buttons when the server does not offer them', (tester) async {
    await pumpApp(tester, '/login');
    expect(find.text('Continue with Google'), findsNothing);
    expect(find.text('Continue with Apple'), findsNothing);
  });

  testWidgets('turn on two-step verification: QR code, code, recovery codes', (tester) async {
    await signUp();
    final container = await pumpApp(tester, '/security');
    await tester.tap(find.text('Two-step verification'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Your password'), 'correct-horse-9');
    await tester.tap(find.widgetWithText(FilledButton, 'Continue'));
    await tester.pumpAndSettle();
    expect(find.text('JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP'), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Code'), '999999');
    await tester.tap(find.widgetWithText(FilledButton, 'Turn on'));
    await tester.pumpAndSettle();
    expect(find.textContaining('not correct'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'Code'), FakeBackend.mfaCode);
    await tester.tap(find.widgetWithText(FilledButton, 'Turn on'));
    await tester.pumpAndSettle();
    expect(find.text('Save your recovery codes'), findsOneWidget);
    expect(find.textContaining(FakeBackend.recoveryCode), findsOneWidget);
    await tester.tap(find.text('I saved them'));
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider).value!.mfaEnabled, isTrue);
    expect(find.text('New recovery codes'), findsOneWidget);
  });

  testWidgets('Google-only account: linked account shown, deletion confirmed by email', (tester) async {
    backend.authOptions = {...backend.authOptions, 'google_client_id': 'web-client'};
    await api().oauthSignIn('google', FakeBackend.googleToken);
    final container = await pumpApp(tester, '/security');
    expect(find.text('Linked accounts'), findsOneWidget);
    expect(find.text('ada@gmail.com'), findsOneWidget);
    expect(find.text('No password'), findsOneWidget);
    await tester.tap(find.text('Unlink'));
    await tester.pumpAndSettle();
    expect(find.textContaining('only way to sign in'), findsOneWidget);

    tester.state<ScaffoldMessengerState>(find.byType(ScaffoldMessenger)).clearSnackBars();
    container.read(routerProvider).go('/settings');
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Delete account'), 200, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('Delete account'));
    await tester.pumpAndSettle();
    expect(find.text('Type your email (ada@gmail.com)'), findsOneWidget);
    await tester.enterText(find.byType(TextField).last, 'ada@gmail.com');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Delete forever'));
    await tester.pumpAndSettle();
    expect(backend.deleteBody, {'confirm_email': 'ada@gmail.com'});
    expect(container.read(authControllerProvider).value, isNull);
  });

  testWidgets('servers that require a confirmed email hold new accounts on the code screen', (tester) async {
    backend.authOptions = {...backend.authOptions, 'email_verification': true, 'email_verification_required': true};
    await signUp();
    backend.users['ada@example.com']!['email_verified'] = false;
    final container = await pumpApp(tester, '/chat');
    expect(find.text('Confirm your email'), findsOneWidget);
    container.read(routerProvider).go('/library');
    await tester.pumpAndSettle();
    expect(find.text('Confirm your email'), findsOneWidget); // still locked

    await tester.enterText(find.byType(TextField), '000000');
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();
    expect(find.textContaining('invalid or has expired'), findsOneWidget);
    await tester.tap(find.text('Send a new code'));
    await tester.pumpAndSettle();
    expect(backend.requests, contains('POST /users/me/email-verification'));

    await tester.enterText(find.byType(TextField), FakeBackend.emailCode);
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();
    expect(container.read(authControllerProvider).value!.emailVerified, isTrue);
    expect(find.text('Confirm your email'), findsNothing);
  });
}
