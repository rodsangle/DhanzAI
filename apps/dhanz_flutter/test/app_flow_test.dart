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

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
  });

  Future<void> pumpApp(WidgetTester tester, {Size size = const Size(1280, 900)}) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
    await tester.pumpAndSettle();
  }

  testWidgets('signed-out users land on the welcome screen', (tester) async {
    await pumpApp(tester);
    expect(find.text('DHANZ AI'), findsOneWidget);
    expect(find.text('Your World. Your Knowledge. Your AI.'), findsOneWidget);
    expect(find.text('Get started'), findsOneWidget);
  });

  testWidgets('signed-out user opens local workspace without creating cloud conversations', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Use local AI on this PC'));
    await tester.pumpAndSettle();
    expect(find.text('DHANZ AI · Local / Cloud'), findsOneWidget);
    expect(find.text('Local'), findsOneWidget);
    expect(find.text('qwen3:8b'), findsOneWidget);
    expect(find.text('Test connection'), findsOneWidget);
    expect(backend.conversations, isEmpty);
    await tester.tap(find.text('qwen3:8b'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('qwen3:14b').last);
    await tester.pumpAndSettle();
    expect(find.text('qwen3:14b'), findsOneWidget);
  });

  testWidgets('register, greet, send a message and see the streamed reply', (tester) async {
    await pumpApp(tester);
    await tester.tap(find.text('Get started'));
    await tester.pumpAndSettle();

    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Ada');
    await tester.enterText(find.widgetWithText(TextFormField, 'Email'), 'ada@example.com');
    await tester.enterText(find.widgetWithText(TextFormField, 'Password'), 'correct-horse-9');
    await tester.tap(find.text('Create account'));
    await tester.pumpAndSettle();

    expect(find.text("Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"), findsOneWidget);

    await tester.enterText(find.widgetWithText(TextField, 'Message Dhanz…'), 'What is DHANZ AI?');
    await tester.pump(); // enable the send button
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(find.text('What is DHANZ AI?'), findsWidgets); // bubble + sidebar title
    expect(find.textContaining('Hello from', findRichText: true), findsOneWidget);
    expect(find.text('echo-1'), findsOneWidget);
    expect(backend.conversations, hasLength(1));
  });

  testWidgets('stored session restores straight into the chat on a phone layout', (tester) async {
    final api = ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);
    await api.register('ada@example.com', 'correct-horse-9', 'Ada');
    await pumpApp(tester, size: const Size(400, 800));
    expect(find.text("Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"), findsOneWidget);
    expect(find.byTooltip('Open navigation menu'), findsOneWidget); // drawer on narrow screens
  });

  test('chat controller creates a conversation on first send', () async {
    final container = ProviderContainer(overrides: overrides());
    addTearDown(container.dispose);
    await container.read(apiClientProvider).register('a@b.co', 'pw-1234567890', 'A');
    await container.read(authControllerProvider.future); // settle the session before chatting
    final controller = container.read(chatControllerProvider.notifier);
    final id = await controller.send('hi there');
    final state = container.read(chatControllerProvider);
    expect(id, isNotNull);
    expect(state.conversationId, id);
    expect(state.streaming, isFalse);
    expect(state.messages.map((m) => m.role), ['user', 'assistant']);
    expect(state.messages.last.content, backend.reply);
    expect(state.messages.first.id, isNot('pending-user'));
  });

  testWidgets('daily local news remembers the chosen area and forces live search', (tester) async {
    final api = ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);
    await api.register('news@example.com', 'correct-horse-9', 'Reader');
    await store.write(StoreKeys.newsLocation, 'Orlando, Florida, USA');
    await pumpApp(tester, size: const Size(400, 800));
    final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).last));
    container.read(chatControllerProvider.notifier).setWebMode(WebMode.off);
    await tester.pump();
    await tester.tap(find.text('Daily local news'));
    await tester.pumpAndSettle();
    expect(find.text('Orlando, Florida, USA'), findsOneWidget);
    await tester.enterText(find.widgetWithText(TextField, 'City or area, state and country'), 'Tampa, Florida, USA');
    await tester.tap(find.text('Get today’s news'));
    await tester.pumpAndSettle();
    expect(await store.read(StoreKeys.newsLocation), 'Tampa, Florida, USA');
    expect(backend.chatBodies.last['content'], contains('Tampa, Florida, USA'));
    expect(backend.chatBodies.last['content'], contains('last 24 hours'));
    expect(backend.chatBodies.last['web'], isTrue);
    expect(container.read(chatControllerProvider).webMode, WebMode.off);
    expect(tester.takeException(), isNull);
  });

  testWidgets('both New chat buttons show a fresh view and clear drafts repeatedly', (tester) async {
    final api = ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);
    await api.register('ada@example.com', 'correct-horse-9', 'Ada');
    await pumpApp(tester);
    final input = find.widgetWithText(TextField, 'Message Dhanz…');
    await tester.enterText(input, 'Keep this conversation');
    await tester.pump();
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
    expect(backend.conversations, hasLength(1));

    await tester.enterText(input, 'Unsent draft');
    await tester.tap(find.text('New chat'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Hello from', findRichText: true), findsNothing);
    expect(find.text("Hello! I'm Dhanz, your personal AI assistant. How can I help you today?"), findsOneWidget);
    expect(tester.widget<TextField>(input).controller!.text, isEmpty);
    expect(backend.conversations, hasLength(1));

    // Already on /chat: navigation alone would leave this draft unchanged.
    await tester.enterText(input, 'Another draft');
    await tester.tap(find.byTooltip('New chat'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(input).controller!.text, isEmpty);
    await tester.enterText(input, 'Third draft');
    await tester.tap(find.text('New chat'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(input).controller!.text, isEmpty);
    expect(backend.conversations, hasLength(1));
  });
}
