import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/main.dart';
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
  ];

  setUp(() async {
    backend = FakeBackend();
    store = MemorySecureStore();
    await ApiClient(
      store: store,
      baseUrl: 'http://test',
      clientFactory: backend.client,
    ).register('ada@example.com', 'correct-horse-9', 'Ada');
  });

  Future<void> pumpApp(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
    await tester.pumpAndSettle();
  }

  test('web mode is sent with the message and research events attach sources', () async {
    final container = ProviderContainer(overrides: overrides());
    addTearDown(container.dispose);
    await container.read(authControllerProvider.future);
    final chat = container.read(chatControllerProvider.notifier);

    await chat.send('hello');
    expect(backend.chatBodies.last.containsKey('web'), isFalse); // Auto: the server decides

    chat.setWebMode(WebMode.always);
    await chat.send('latest chips');
    expect(backend.chatBodies.last['web'], isTrue);
    final reply = container.read(chatControllerProvider).messages.last;
    expect(reply.citations.single.title, '2nm chips arrive');
    expect(reply.citations.single.siteName, 'Chip Times');
    expect(container.read(chatControllerProvider).researchStatus, isNull);

    chat.setWebMode(WebMode.off);
    await chat.send('no web please');
    expect(backend.chatBodies.last['web'], isFalse);
  });

  testWidgets('sources appear under a researched answer', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.byTooltip('Web research'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Web: Always').last);
    await tester.pumpAndSettle();

    await tester.enterText(find.widgetWithText(TextField, 'Message Dhanz…'), 'latest semiconductor news');
    await tester.pump();
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(find.text('Sources'), findsOneWidget);
    expect(find.text('2nm chips arrive'), findsOneWidget);
    expect(find.textContaining('Chip Times'), findsOneWidget);
  });

  testWidgets('knowledge library: add a page, see it listed, and see refusals explained', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Knowledge library'));
    await tester.pumpAndSettle();
    expect(find.text('Your library is empty'), findsOneWidget);

    await tester.tap(find.text('Add page'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'garden.example/tomatoes');
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();
    expect(find.text('Growing tomatoes'), findsOneWidget);
    expect(backend.documents.single['url'], 'https://garden.example/tomatoes');

    await tester.tap(find.text('Add page'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'https://blocked.example/x');
    await tester.tap(find.widgetWithText(FilledButton, 'Add'));
    await tester.pumpAndSettle();
    expect(find.textContaining('robots.txt'), findsOneWidget);
  });
}
