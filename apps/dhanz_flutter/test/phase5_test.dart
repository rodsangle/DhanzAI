import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/app_version.dart';
import 'package:dhanz_ai/core/platform/updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;

  List<Override> overrides() => [
    secureStoreProvider.overrideWithValue(store),
    apiClientProvider.overrideWith(
      (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
    ),
    appVersionProvider.overrideWith((ref) async => '0.5.0'),
    updatePlatformProvider.overrideWithValue(null),
  ];

  ApiClient api() => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
  });

  Future<void> signUp([String email = 'owner@example.com']) => api().register(email, 'correct-horse-9', 'Owner');

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

  group('account security', () {
    testWidgets('devices can be listed and signed out', (tester) async {
      await signUp();
      await pumpApp(tester, '/security');
      expect(find.text('Windows (this device)'), findsOneWidget);
      expect(find.text('Android'), findsOneWidget);

      await tester.tap(find.widgetWithText(TextButton, 'Sign out'));
      await tester.pumpAndSettle();
      expect(backend.requests, contains('DELETE /users/me/sessions/session-phone'));
      expect(find.text('Android'), findsNothing);
      expect(find.text('Android has been signed out.'), findsOneWidget);
    });

    testWidgets('change password: wrong current password is reported, then it succeeds', (tester) async {
      await signUp();
      await pumpApp(tester, '/security');
      await tester.tap(find.text('Change password'));
      await tester.pumpAndSettle();

      await tester.enterText(find.widgetWithText(TextFormField, 'Current password'), 'not-my-password');
      await tester.enterText(find.widgetWithText(TextFormField, 'New password'), 'brand-new-pass-1');
      await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
      await tester.pumpAndSettle();
      expect(find.text('Current password is incorrect'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextFormField, 'Current password'), 'correct-horse-9');
      await tester.tap(find.widgetWithText(FilledButton, 'Change password'));
      await tester.pumpAndSettle();
      expect(find.text('Password changed. Other devices have been signed out.'), findsOneWidget);
      expect(backend.passwords['owner@example.com'], 'brand-new-pass-1');
    });

    testWidgets('forgot password: code by email, then a new password', (tester) async {
      await signUp('ada@example.com');
      await store.deleteAll(); // signed out
      await pumpApp(tester, '/login');
      await tester.tap(find.text('Forgot your password?'));
      await tester.pumpAndSettle();

      await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'ada@example.com');
      await tester.tap(find.text('Send code'));
      await tester.pumpAndSettle();
      expect(backend.resetRequestedFor, 'ada@example.com');
      expect(find.textContaining('we emailed it a code'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextFormField, 'Code from the email'), 'WRONG-00000');
      await tester.enterText(find.widgetWithText(TextFormField, 'New password'), 'fresh-pass-77');
      await tester.tap(find.text('Set new password'));
      await tester.pumpAndSettle();
      expect(find.textContaining('invalid or has expired'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextFormField, 'Code from the email'), FakeBackend.resetCode);
      await tester.tap(find.text('Set new password'));
      await tester.pumpAndSettle();
      expect(find.text('Password changed. Sign in with your new password.'), findsOneWidget);
      expect(find.text('Welcome back'), findsOneWidget);
      expect(backend.passwords['ada@example.com'], 'fresh-pass-77');
    });
  });

  group('privacy', () {
    test('temporary chats are created as such and the choice resets for the next new chat', () async {
      await signUp();
      final c = ProviderContainer(overrides: overrides());
      addTearDown(c.dispose);
      await c.read(authControllerProvider.future);
      final chat = c.read(chatControllerProvider.notifier)..setTemporary(true);
      final id = await chat.send('Something private');
      expect(backend.conversationBodies.single['temporary'], isTrue);
      expect(backend.conversations[id]!['temporary'], isTrue);

      chat.setTemporary(false); // ignored once the chat exists
      expect(c.read(chatControllerProvider).temporary, isTrue);
      await chat.open(null);
      expect(c.read(chatControllerProvider).temporary, isFalse);
      await chat.open(id);
      expect(c.read(chatControllerProvider).temporary, isTrue);
    });

    test('conversation retention can be set and cleared', () async {
      await signUp();
      final user = await api().updateMe(retentionDays: 30);
      expect(user.retentionDays, 30);
      expect((await api().updateMe(retentionDays: 0)).retentionDays, isNull);
    });

    testWidgets('temporary chat toggle shows the banner', (tester) async {
      await signUp();
      await pumpApp(tester, '/chat');
      await tester.tap(find.byTooltip('Temporary chat'));
      await tester.pumpAndSettle();
      expect(find.text('Temporary chat'), findsOneWidget);
      expect(find.textContaining('deleted automatically after a day'), findsOneWidget);
    });
  });

  group('administration', () {
    testWidgets('the first account administers the server', (tester) async {
      await signUp();
      await api().register('ada@example.com', 'correct-horse-9', 'Ada');
      await api().login('owner@example.com', 'correct-horse-9'); // back to the owner's session
      await pumpApp(tester, '/settings');
      await tester.scrollUntilVisible(find.text('Administration'), 300, scrollable: find.byType(Scrollable).first);
      expect(find.text('Administration'), findsOneWidget);

      await tester.tap(find.text('Administration'));
      await tester.pumpAndSettle();
      expect(find.text('Accounts'), findsWidgets);
      expect(find.text('2'), findsOneWidget); // two accounts
      expect(find.textContaining('ada@example.com'), findsOneWidget);
      expect(find.text('You'), findsOneWidget);

      await tester.tap(find.byTooltip('Manage Ada'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Deactivate account'));
      await tester.pumpAndSettle();
      expect(backend.users['ada@example.com']!['is_active'], isFalse);
      expect(find.textContaining('deactivated'), findsOneWidget);
    });

    testWidgets('other users cannot open the admin screen', (tester) async {
      await signUp();
      backend.users['owner@example.com']!['role'] = 'user';
      await pumpApp(tester, '/admin');
      expect(find.text('Administration'), findsNothing);
      expect(find.text('Settings'), findsOneWidget);
    });
  });
}
