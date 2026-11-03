import 'dart:async';
import 'dart:typed_data';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/files.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/features/projects/projects_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

class DelayedFileApi extends ApiClient {
  DelayedFileApi(MemorySecureStore store, FakeBackend backend)
    : super(store: store, baseUrl: 'http://test', clientFactory: backend.client);
  final uploads = <Completer<void>>[];

  @override
  Future<KnowledgeDocument> uploadFile(String filename, Uint8List bytes, {String? projectId}) async {
    final ready = Completer<void>();
    uploads.add(ready);
    await ready.future;
    return super.uploadFile(filename, bytes, projectId: projectId);
  }
}

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;
  late DelayedFileApi api;
  final bytes = Uint8List.fromList([37, 80, 68, 70]);
  const prompt = 'Convert this PDF into an Excel workbook. Preserve all rows.';

  setUp(() async {
    backend = FakeBackend();
    store = MemorySecureStore();
    api = DelayedFileApi(store, backend);
    await api.register('ada@example.com', 'correct-horse-9', 'Ada');
    addTearDown(api.close);
  });

  Future<ProviderContainer> setup() async {
    final container = ProviderContainer(
      overrides: [secureStoreProvider.overrideWithValue(store), apiClientProvider.overrideWithValue(api)],
    );
    addTearDown(container.dispose);
    await container.read(authControllerProvider.future);
    container.listen(chatControllerProvider, (_, _) {});
    return container;
  }

  Future<void> tick() => Future<void>.delayed(Duration.zero);

  test('one request contains the exact instruction and PDF after reading/upload finishes', () async {
    final c = await setup();
    final chat = c.read(chatControllerProvider.notifier);
    final reading = Completer<List<PickedFile>>();
    final upload = chat.attachFiles(() => reading.future);
    final sending = chat.send(prompt);
    expect(c.read(chatControllerProvider).sending, isTrue);
    expect(backend.chatBodies, isEmpty);
    reading.complete([(name: 'training.pdf', bytes: bytes)]);
    await tick();
    expect(backend.chatBodies, isEmpty, reason: 'server upload and OCR are still in progress');
    api.uploads.single.complete();
    await upload;
    expect(await sending, isNotNull);
    expect(backend.chatBodies.single['content'], prompt);
    expect(backend.chatBodies.single['attachment_ids'], [backend.documents.single['id']]);
  });

  test('double send while uploading cannot create duplicate messages', () async {
    final c = await setup();
    final chat = c.read(chatControllerProvider.notifier);
    final upload = chat.attachFile('training.pdf', bytes);
    await tick();
    final first = chat.send(prompt);
    expect(await chat.send(prompt), isNull);
    api.uploads.single.complete();
    await upload;
    await first;
    expect(backend.chatBodies, hasLength(1));
  });

  test('upload failure blocks the prompt instead of sending it without its file', () async {
    final c = await setup();
    final chat = c.read(chatControllerProvider.notifier);
    final upload = chat.attachFile('training.pdf', bytes);
    await tick();
    final sending = chat.send(prompt);
    api.uploads.single.completeError(ApiException(422, 'OCR extraction failed'));
    await upload;
    expect(await sending, isNull);
    expect(backend.chatBodies, isEmpty);
    expect(backend.conversationBodies, isEmpty);
    expect(c.read(chatControllerProvider).failedAttachments, ['training.pdf']);
    expect(c.read(chatControllerProvider).sending, isFalse);
  });

  for (final change in ['chat', 'project', 'account']) {
    test('switching $change cancels a queued send and ignores its late file', () async {
      final c = await setup();
      final chat = c.read(chatControllerProvider.notifier);
      final upload = chat.attachFile('training.pdf', bytes);
      await tick();
      final sending = chat.send(prompt);
      if (change == 'chat') {
        await chat.open(null);
      } else if (change == 'project') {
        c.read(selectedProjectProvider.notifier).select('another-project');
      } else {
        await c.read(authControllerProvider.notifier).logout();
      }
      await tick();
      expect(await sending, isNull);
      api.uploads.single.complete();
      await upload;
      expect(backend.chatBodies, isEmpty);
      expect(c.read(chatControllerProvider).attachments, isEmpty);
      expect(c.read(chatControllerProvider).uploading, 0);
    });
  }

  test('cancelling pending send retains the completed file for an explicit retry', () async {
    final c = await setup();
    final chat = c.read(chatControllerProvider.notifier);
    final upload = chat.attachFile('training.pdf', bytes);
    await tick();
    final sending = chat.send(prompt);
    chat.cancelPendingSend();
    api.uploads.single.complete();
    await upload;
    expect(await sending, isNull);
    expect(backend.chatBodies, isEmpty);
    expect(c.read(chatControllerProvider).attachments, hasLength(1));
    await chat.send(prompt);
    expect(backend.chatBodies, hasLength(1));
  });

  for (final fail in [false, true]) {
    testWidgets('Send during upload ${fail ? 'preserves failed draft' : 'queues the typed instruction with its PDF'}', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [secureStoreProvider.overrideWithValue(store), apiClientProvider.overrideWithValue(api)],
          child: const DhanzApp(),
        ),
      );
      await tester.pumpAndSettle();
      final c = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
      final upload = c.read(chatControllerProvider.notifier).attachFile('training.pdf', bytes);
      await tester.pump();
      await tester.enterText(find.widgetWithText(TextField, 'Message Dhanz…'), prompt);
      await tester.pump();
      await tester.tap(find.byTooltip('Send'));
      await tester.pump();
      expect(backend.chatBodies, isEmpty);
      expect(find.byTooltip('Cancel pending send'), findsOneWidget);
      expect(tester.widget<TextField>(find.widgetWithText(TextField, 'Message Dhanz…')).controller!.text, prompt);
      if (fail) {
        api.uploads.single.completeError(ApiException(422, 'OCR extraction failed'));
      } else {
        api.uploads.single.complete();
      }
      await tester.pumpAndSettle();
      await upload;
      if (fail) {
        expect(backend.chatBodies, isEmpty);
        expect(tester.widget<TextField>(find.widgetWithText(TextField, 'Message Dhanz…')).controller!.text, prompt);
        expect(find.textContaining('training.pdf — upload failed'), findsOneWidget);
      } else {
        expect(backend.chatBodies.single['content'], prompt);
        expect(backend.chatBodies.single['attachment_ids'], [backend.documents.single['id']]);
      }
    });
  }
}
