import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

/// A model chosen in the picker that the server later stops offering must not break every message.
void main() {
  late FakeBackend backend;
  late MemorySecureStore store;

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
  });

  ApiClient api() => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);

  Future<ProviderContainer> pumpApp(WidgetTester tester) async {
    await api().register('ada@example.com', 'correct-horse-9', 'Ada');
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

  testWidgets('a chosen model missing from the server list is sent as Auto', (tester) async {
    final container = await pumpApp(tester);
    container.read(chatControllerProvider.notifier).selectModel('openai:gpt-6.1-sol');

    await sendMessage(tester, 'hello');
    expect(backend.chatBodies.single.containsKey('provider'), isFalse);
    expect(container.read(chatControllerProvider).modelKey, isNull);
  });

  testWidgets('a model the server refuses as unavailable switches the chat back to Auto', (tester) async {
    backend.extraModels.add({
      'key': 'openai:gpt-6.1-sol',
      'provider': 'openai',
      'model': 'gpt-6.1-sol',
      'display_name': 'gpt-6.1-sol',
      'capabilities': ['chat'],
      'cost_tier': 2,
      'context_window': 128000,
    });
    backend.retiredModels.add('openai:gpt-6.1-sol');
    final container = await pumpApp(tester);
    container.read(chatControllerProvider.notifier).selectModel('openai:gpt-6.1-sol');

    await sendMessage(tester, 'first try');
    expect(backend.chatBodies.last['model'], 'gpt-6.1-sol');
    expect(container.read(chatControllerProvider).modelKey, isNull);
    expect(find.textContaining('Dhanz switched to Auto'), findsOneWidget);

    await tester.pump(const Duration(seconds: 10)); // the error message times out
    await tester.pumpAndSettle();
    await sendMessage(tester, 'second try');
    expect(backend.chatBodies, hasLength(2));
    expect(backend.chatBodies.last.containsKey('provider'), isFalse);
  });
}
