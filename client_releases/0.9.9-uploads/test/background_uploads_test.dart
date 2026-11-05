import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/folder_types.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/core/uploads/upload_queue.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/features/library/uploads_screen.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const owner = User(id: 'owner', email: 'owner@example.test', displayName: 'Owner', role: 'user', routingPolicy: 'balanced');
class UploadAuth extends AuthController {
  @override
  Future<User?> build() async => owner;
  void signOutLocally() => state = const AsyncData(null);
}

class UploadApi extends ApiClient {
  UploadApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  final calls = <({String name, String? project, Uint8List bytes, Completer<KnowledgeDocument> result})>[];
  @override
  Future<KnowledgeDocument> uploadFile(String filename, Uint8List bytes, {String? projectId, bool Function()? isCurrentSession}) {
    final result = Completer<KnowledgeDocument>();
    calls.add((name: filename, project: projectId, bytes: bytes, result: result));
    return result.future;
  }
  @override
  Future<ConversationDetail> conversation(String id) async => ConversationDetail(
    summary: ConversationSummary(id: id, title: id, pinned: false, updatedAt: DateTime.utc(2026)), messages: const []);
  @override
  Future<List<KnowledgeDocument>> documents() async => [];
}

KnowledgeDocument document(String name) => KnowledgeDocument(id: name, url: 'upload:$name', title: name,
  retrievedAt: DateTime.utc(2026), addedVia: 'upload', kind: 'file', fileType: 'text');

Future<ProviderContainer> containerFor(UploadApi api) async {
  final container = ProviderContainer(overrides: [apiClientProvider.overrideWithValue(api), authControllerProvider.overrideWith(UploadAuth.new)]);
  await container.read(authControllerProvider.future);
  container.read(uploadQueueProvider);
  return container;
}

Future<void> tick() => Future<void>.delayed(Duration.zero);

void main() {
  test('uploads continue after listeners leave; original project is captured and failures do not stop later files', () async {
    final api = UploadApi();
    final container = await containerFor(api);
    addTearDown(container.dispose);
    final queue = container.read(uploadQueueProvider.notifier);
    final listener = container.listen(uploadQueueProvider, (_, _) {});
    queue.files([(name: 'first.txt', bytes: Uint8List(3)), (name: 'second.txt', bytes: Uint8List(4))],
      ticket: queue.ticket(), projectId: 'original-project');
    listener.close(); // Library route removed.
    await tick();
    expect(api.calls.length, 1);
    api.calls[0].result.completeError(ApiException(0, 'Connection lost'));
    await tick();
    expect(api.calls.length, 2);
    api.calls[1].result.complete(document('second.txt'));
    await tick();
    final jobs = container.read(uploadQueueProvider);
    expect(jobs.map((j) => j.status), [UploadStatus.failed, UploadStatus.completed]);
    expect(api.calls.every((call) => call.project == 'original-project'), isTrue);
    expect(api.calls.length, 2); // The uncertain first request was not replayed.
  });

  test('new chat does not receive an old upload; returning to its conversation restores the attachment', () async {
    final api = UploadApi();
    final container = await containerFor(api);
    addTearDown(container.dispose);
    final chat = container.read(chatControllerProvider.notifier);
    await chat.open('original');
    final upload = chat.attachFile('original.txt', Uint8List(2));
    await tick();
    await chat.open(null);
    expect(container.read(chatControllerProvider).uploading, 0);
    api.calls.single.result.complete(document('original.txt'));
    await upload;
    expect(container.read(chatControllerProvider).attachments, isEmpty);
    await chat.open('original');
    expect(container.read(chatControllerProvider).attachments.single.id, 'original.txt');
    expect(container.read(chatControllerProvider).uploading, 0);
    chat.removeAttachment('original.txt');
    expect(container.read(chatControllerProvider).attachments, isEmpty);
  });

  test('folder preparation and upload survive starting a new chat and preserve relative paths', () async {
    final api = UploadApi();
    final container = await containerFor(api);
    addTearDown(container.dispose);
    final chat = container.read(chatControllerProvider.notifier);
    await chat.open('folder-chat');
    final queue = container.read(uploadQueueProvider.notifier);
    final reading = Completer<Uint8List>();
    queue.folder([FolderFile('project/src/a.txt', 3, () => reading.future)],
      ticket: queue.ticket(), target: chat.uploadTarget, projectId: 'fixed-project');
    await tick();
    await chat.open(null);
    reading.complete(Uint8List.fromList(utf8.encode('abc')));
    await tick();
    expect(api.calls.single.name, 'project.dhanz-folder.zip');
    final archive = ZipDecoder().decodeBytes(api.calls.single.bytes);
    expect(archive.single.name, 'project/src/a.txt');
    expect(utf8.decode(archive.single.content), 'abc');
    api.calls.single.result.complete(document('folder'));
    await tick();
    expect(container.read(uploadQueueProvider).single.status, UploadStatus.completed);
    expect(container.read(chatControllerProvider).attachments, isEmpty);
  });

  test('sign-out discards pending work and ignores an in-flight old-account result', () async {
    final api = UploadApi();
    final container = await containerFor(api);
    addTearDown(container.dispose);
    final queue = container.read(uploadQueueProvider.notifier);
    final ticket = queue.ticket();
    queue.files([(name: 'first', bytes: Uint8List(1)), (name: 'second', bytes: Uint8List(1))], ticket: ticket);
    await tick();
    (container.read(authControllerProvider.notifier) as UploadAuth).signOutLocally();
    expect(container.read(uploadQueueProvider), isEmpty);
    api.calls.single.result.complete(document('old-account'));
    await tick();
    expect(api.calls.length, 1);
    expect(container.read(uploadQueueProvider), isEmpty);
    expect(queue.accepts(ticket), isFalse);
  });

  test('guarded upload does not send after session changes and never refreshes/replays a rejected POST', () async {
    var requests = 0;
    final client = MockClient((request) async { requests++; return http.Response('{}', 401); });
    final api = ApiClient(store: MemorySecureStore(), baseUrl: 'https://example.test', clientFactory: () => client);
    await expectLater(api.uploadFile('a.txt', Uint8List(1), isCurrentSession: () => false), throwsA(isA<ApiException>()));
    expect(requests, 0);
    await expectLater(api.uploadFile('a.txt', Uint8List(1), isCurrentSession: () => true), throwsA(isA<ApiException>()));
    expect(requests, 1);
    api.close();
  });

  testWidgets('navigation away from the uploads page leaves the queue running', (tester) async {
    final api = UploadApi();
    final container = await containerFor(api);
    addTearDown(container.dispose);
    final router = GoRouter(initialLocation: '/uploads', routes: [
      GoRoute(path: '/uploads', builder: (_, _) => const UploadsScreen()),
      GoRoute(path: '/chat', builder: (_, _) => const Scaffold(body: Text('New chat page'))),
    ]);
    addTearDown(router.dispose);
    await tester.pumpWidget(UncontrolledProviderScope(container: container, child: MaterialApp.router(routerConfig: router)));
    final queue = container.read(uploadQueueProvider.notifier);
    queue.files([(name: 'background.txt', bytes: Uint8List(2))], ticket: queue.ticket());
    await tester.pump();
    await tester.tap(find.byIcon(Icons.arrow_back));
    await tester.pump();
    expect(find.text('New chat page'), findsOneWidget);
    api.calls.single.result.complete(document('background.txt'));
    await tester.pump();
    router.go('/uploads');
    await tester.pumpAndSettle();
    expect(find.text('Saved to library'), findsOneWidget);
  });
}
