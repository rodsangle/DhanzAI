import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
  });

  ApiClient api() => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);

  Future<ProviderContainer> pumpApp(WidgetTester tester, {bool signedIn = true}) async {
    if (signedIn) await api().register('ada@example.com', 'correct-horse-9', 'Ada');
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [secureStoreProvider.overrideWithValue(store), apiClientProvider.overrideWith((ref) => api())],
        child: const DhanzApp(),
      ),
    );
    await tester.pumpAndSettle();
    return ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
  }

  Future<void> sendMessage(WidgetTester tester, String text) async {
    await tester.enterText(find.widgetWithText(TextField, 'Message Dhanz…'), text);
    await tester.pump();
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
  }

  String location(ProviderContainer c) => c.read(routerProvider).routerDelegate.currentConfiguration.uri.path;

  testWidgets('Branch in new chat copies the chat up to that reply and opens it', (tester) async {
    final container = await pumpApp(tester);
    await sendMessage(tester, 'first question');
    await sendMessage(tester, 'second question');
    final original = location(container);
    expect(backend.conversations, hasLength(1));

    await tester.tap(find.byTooltip('Branch in new chat').last); // the first reply (the list is newest-first)
    await tester.pumpAndSettle();
    expect(backend.conversations, hasLength(2));
    expect(location(container), isNot(original));
    final branch = backend.conversations.values.firstWhere((c) => (c['title'] as String).startsWith('Branch'));
    expect((branch['messages'] as List), hasLength(2)); // question 1 and its reply only
    expect(find.text('second question'), findsWidgets); // still in the history sidebar via the original title
  });

  testWidgets('archiving hides a chat from the history and Settings restores it', (tester) async {
    final container = await pumpApp(tester);
    await sendMessage(tester, 'keep but hide');
    final id = backend.conversations.keys.single;
    expect(find.byIcon(Icons.chat_bubble_outline), findsWidgets);

    await tester.tap(find.byTooltip('Conversation options').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Archive').last);
    await tester.pumpAndSettle();
    expect(backend.archived.keys, [id]);
    expect(find.byTooltip('Conversation options'), findsNothing); // gone from the history

    container.read(routerProvider).go('/archived');
    await tester.pumpAndSettle();
    expect(find.text('Archived chats'), findsOneWidget);
    await tester.tap(find.text('Restore'));
    await tester.pumpAndSettle();
    expect(backend.archived, isEmpty);
    expect(find.text('No archived chats.'), findsOneWidget);
  });

  testWidgets('Share chat creates a link, the public page reads it, and revoking removes it', (tester) async {
    final copied = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied.add((call.arguments as Map)['text'] as String);
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
    final container = await pumpApp(tester);
    await sendMessage(tester, 'what is a share link?');

    await tester.tap(find.byTooltip('Share chat'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Messages you send later are not shared'), findsOneWidget);
    await tester.tap(find.text('Create link'));
    await tester.pumpAndSettle();
    final token = backend.shares.keys.single;
    expect(find.text('http://test/app/#/share/$token'), findsOneWidget);
    await tester.tap(find.text('Copy link'));
    await tester.pumpAndSettle();
    expect(copied, ['http://test/app/#/share/$token']);
    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();

    container.read(routerProvider).go('/share/$token');
    await tester.pumpAndSettle();
    expect(find.text('Shared chat'), findsOneWidget);
    expect(find.text('what is a share link?'), findsWidgets); // title and message

    container.read(routerProvider).go('/shared-links');
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Revoke link'));
    await tester.pumpAndSettle();
    expect(backend.shares, isEmpty);
    expect(find.text('You have not shared any chats.'), findsOneWidget);
  });

  testWidgets('a shared link opens without signing in', (tester) async {
    backend.shares['tok-public'] = {
      'token': 'tok-public',
      'title': 'Trip ideas',
      'created_at': '2026-11-13T10:00:00Z',
      'count': 2,
      'messages': [
        {'role': 'user', 'content': 'Ideas for Lisbon?', 'model': null, 'sources': []},
        {'role': 'assistant', 'content': 'Visit **Alfama**.', 'model': 'echo-1', 'sources': []},
      ],
    };
    final container = await pumpApp(tester, signedIn: false);
    container.read(routerProvider).go('/share/tok-public');
    await tester.pumpAndSettle();
    expect(location(container), '/share/tok-public'); // not redirected to /welcome
    expect(find.text('Trip ideas'), findsOneWidget);
    expect(find.text('Ideas for Lisbon?'), findsOneWidget);

    container.read(routerProvider).go('/share/unknown');
    await tester.pumpAndSettle();
    expect(find.text('This shared chat does not exist or was removed.'), findsOneWidget);
  });

  testWidgets('older servers without the feature: history still loads and actions explain why', (tester) async {
    backend.conversationExtras = false;
    await pumpApp(tester);
    await sendMessage(tester, 'hello');
    expect(find.byTooltip('Conversation options'), findsOneWidget); // history works

    await tester.tap(find.byTooltip('Share chat'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Create link'));
    await tester.pumpAndSettle();
    expect(find.text('This needs the latest DHANZ server update (conversation extras).'), findsOneWidget);
  });
}
