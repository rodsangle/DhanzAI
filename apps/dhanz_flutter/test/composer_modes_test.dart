import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/chat/composer.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
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

  Future<ProviderContainer> pumpSignedIn(WidgetTester tester) async {
    await ApiClient(
      store: store,
      baseUrl: 'http://test',
      clientFactory: backend.client,
    ).register('ada@example.com', 'correct-horse-9', 'Ada');
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          secureStoreProvider.overrideWithValue(store),
          apiClientProvider.overrideWith(
            (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
          ),
        ],
        child: const DhanzApp(),
      ),
    );
    await tester.pumpAndSettle();
    return ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
  }

  test('photo and video requests are worded for the assistant; chat and code text is unchanged', () {
    expect(creationRequest(ComposerMode.photo, 'a red bike'), 'Create an image: a red bike');
    expect(creationRequest(ComposerMode.video, 'waves at dusk'), 'Create a video: waves at dusk');
    expect(creationRequest(ComposerMode.chat, 'hello'), 'hello');
  });

  testWidgets('one chat box sends chat, photo and video requests into the same conversation', (tester) async {
    await pumpSignedIn(tester);
    expect(find.byKey(const ValueKey('composer-mode')), findsOneWidget);

    await tester.tap(find.text('Photo'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Describe the photo to create…'), 'a red bike');
    await tester.pump();
    await tester.tap(find.byTooltip('Create photo'));
    await tester.pumpAndSettle();
    expect(backend.chatBodies.last['content'], 'Create an image: a red bike');
    expect(backend.conversations, hasLength(1));

    await tester.tap(find.text('Video'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Describe the video to create…'), 'waves at dusk');
    await tester.pump();
    await tester.tap(find.byTooltip('Create video'));
    await tester.pumpAndSettle();
    expect(backend.chatBodies.last['content'], 'Create a video: waves at dusk');
    expect(backend.conversations, hasLength(1)); // same conversation

    await tester.tap(find.text('Chat'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Message Dhanz…'), 'thanks');
    await tester.pump();
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();
    expect(backend.chatBodies.last['content'], 'thanks');
    expect(backend.chatBodies, hasLength(3));
  });

  testWidgets('Code mode hands the task to the coding workspace instead of chatting', (tester) async {
    final container = await pumpSignedIn(tester);
    await tester.tap(find.text('Code'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Describe the coding task…'), 'add a login page');
    await tester.pump();
    await tester.tap(find.byTooltip('Open in the coding workspace'));
    await tester.pump();
    expect(backend.chatBodies, isEmpty);
    expect(container.read(routerProvider).routerDelegate.currentConfiguration.uri.path, '/coding');
  });
}
