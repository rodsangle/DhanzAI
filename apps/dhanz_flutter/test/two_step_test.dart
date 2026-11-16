import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/app_version.dart';
import 'package:dhanz_ai/core/platform/updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

/// Two-step verification by emailed code, "remember this device" and the remembered-devices list.
void main() {
  late FakeBackend backend;
  late MemorySecureStore store;

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
    backend.authOptions = {...backend.authOptions, 'mfa_email': true, 'trusted_device_days': 30};
  });

  ApiClient api() => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);

  Future<void> signUp({String? method}) async {
    await api().register('ada@example.com', 'correct-horse-9', 'Ada');
    if (method != null) {
      backend.users['ada@example.com']!
        ..['mfa_enabled'] = true
        ..['mfa_method'] = method;
    }
  }

  Future<ProviderContainer> pumpApp(WidgetTester tester, String location) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          secureStoreProvider.overrideWithValue(store),
          apiClientProvider.overrideWith((ref) => api()),
          appVersionProvider.overrideWith((ref) async => '0.7.0'),
          updatePlatformProvider.overrideWithValue(null),
        ],
        child: const DhanzApp(),
      ),
    );
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
    container.read(routerProvider).go(location);
    await tester.pumpAndSettle();
    return container;
  }

  Future<void> signIn(WidgetTester tester) async {
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'ada@example.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Password'), 'correct-horse-9');
    await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
    await tester.pumpAndSettle();
  }

  testWidgets('emailed sign-in code, resend, and remember this device', (tester) async {
    await signUp(method: 'email');
    await store.deleteAll();
    final container = await pumpApp(tester, '/login');
    await signIn(tester);
    expect(find.text('Two-step verification'), findsOneWidget);
    expect(find.textContaining('We emailed a 6-digit code to a*a@example.com'), findsOneWidget);
    expect(find.text('No access to your email? Use a recovery code'), findsOneWidget);

    await tester.tap(find.text('Send a new code'));
    await tester.pumpAndSettle();
    expect(find.text('We sent a new code to a*a@example.com.'), findsOneWidget);
    expect(backend.requests, contains('POST /auth/mfa/resend'));

    await tester.tap(find.byKey(const Key('remember-device')));
    await tester.pumpAndSettle();
    expect(find.text('Remember this device for 30 days'), findsOneWidget);
    await tester.enterText(find.byType(TextField), FakeBackend.emailMfaCode);
    await tester.tap(find.widgetWithText(FilledButton, 'Verify'));
    await tester.pumpAndSettle();
    expect(backend.mfaVerifyBodies.last['remember_device'], isTrue);
    expect(container.read(authControllerProvider).value, isNotNull);
    expect(await store.read(StoreKeys.trustedDevice), 'device-token-1');

    // Next sign-in on this device skips the second step.
    await container.read(authControllerProvider.notifier).logout();
    await tester.pumpAndSettle();
    expect(await store.read(StoreKeys.trustedDevice), 'device-token-1'); // kept on sign-out
    container.read(routerProvider).go('/login');
    await tester.pumpAndSettle();
    await signIn(tester);
    expect(backend.loginBodies.last['trusted_device_token'], 'device-token-1');
    expect(find.text('Two-step verification'), findsNothing);
    expect(container.read(authControllerProvider).value, isNotNull);
  });

  testWidgets('without the server offering it, there is no remember-device option', (tester) async {
    backend.authOptions = {...backend.authOptions, 'trusted_device_days': 0};
    await signUp(method: 'totp');
    await store.deleteAll();
    await pumpApp(tester, '/login');
    await signIn(tester);
    expect(find.text('Enter the 6-digit code from your authenticator app.'), findsOneWidget);
    expect(find.byKey(const Key('remember-device')), findsNothing);
    expect(find.text('Send a new code'), findsNothing);
  });

  testWidgets('turn on two-step verification with email codes', (tester) async {
    await signUp();
    final container = await pumpApp(tester, '/security');
    await tester.tap(find.text('Two-step verification'));
    await tester.pumpAndSettle();
    expect(find.text('Authenticator app (recommended)'), findsOneWidget);
    await tester.tap(find.byKey(const Key('mfa-method-email')));
    await tester.enterText(find.widgetWithText(TextField, 'Your password'), 'correct-horse-9');
    await tester.tap(find.widgetWithText(FilledButton, 'Continue'));
    await tester.pumpAndSettle();
    expect(find.text('Check your email'), findsOneWidget);
    expect(find.textContaining('We sent a code to a*a@example.com.'), findsOneWidget);

    await tester.enterText(find.byKey(const Key('mfa-email-setup-code')), '000000');
    await tester.tap(find.widgetWithText(FilledButton, 'Turn on'));
    await tester.pumpAndSettle();
    expect(find.textContaining('invalid or has expired'), findsOneWidget);
    await tester.enterText(find.byKey(const Key('mfa-email-setup-code')), FakeBackend.emailMfaCode);
    await tester.tap(find.widgetWithText(FilledButton, 'Turn on'));
    await tester.pumpAndSettle();
    expect(find.text('Save your recovery codes'), findsOneWidget);
    await tester.tap(find.text('I saved them'));
    await tester.pumpAndSettle();
    final user = container.read(authControllerProvider).value!;
    expect(user.mfaEnabled && user.mfaByEmail, isTrue);
    expect(find.text('On: signing in also needs a code we email to you'), findsOneWidget);
  });

  testWidgets('servers without email codes offer only the authenticator app', (tester) async {
    backend.authOptions = {...backend.authOptions, 'mfa_email': false};
    await signUp();
    await pumpApp(tester, '/security');
    await tester.tap(find.text('Two-step verification'));
    await tester.pumpAndSettle();
    expect(find.text('Code by email'), findsNothing);
    expect(find.textContaining('authenticator app on your phone'), findsOneWidget);
  });

  testWidgets('turning off email codes sends a code first; remembered devices can be forgotten', (tester) async {
    await signUp(method: 'email');
    backend.trustedDevices['device-token-9'] = {
      'id': 'dev-1',
      'email': 'ada@example.com',
      'label': 'Chrome on Windows',
    };
    await pumpApp(tester, '/security');
    expect(find.text('Remembered devices'), findsOneWidget);
    expect(find.text('Chrome on Windows'), findsOneWidget);
    await tester.tap(find.widgetWithText(TextButton, 'Forget'));
    await tester.pumpAndSettle();
    expect(backend.trustedDevices, isEmpty);
    expect(find.text('Remembered devices'), findsNothing);

    final sentBefore = backend.mfaEmailsSent;
    await tester.tap(find.text('Two-step verification'));
    await tester.pumpAndSettle();
    expect(backend.mfaEmailsSent, sentBefore + 1);
    expect(find.text('Code we emailed you'), findsOneWidget);
    await tester.enterText(find.byType(TextField), FakeBackend.emailMfaCode);
    await tester.tap(find.widgetWithText(FilledButton, 'Turn off'));
    await tester.pumpAndSettle();
    expect(find.text('Two-step verification is off.'), findsOneWidget);
  });
}
