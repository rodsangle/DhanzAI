import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/coding/coding_screen.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class CodingApi extends ApiClient {
  CodingApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  int published = 0;
  int createdCalls = 0;
  Map<String, dynamic>? created;
  final draft = <String, dynamic>{
    'id': 'draft',
    'title': 'Existing task',
    'status': 'review',
    'project_status': 'complete',
    'repository': 'owner/demo',
    'base_branch': 'main',
    'base_sha': 'base-commit',
    'repair_count': 0,
    'project_id': 'project',
    'review_hash': 'review-hash',
    'files': <Map<String, dynamic>>[
      {'path': 'index.html', 'content': '<p>Updated</p>'},
    ],
    'diffs': <Map<String, dynamic>>[
      {'path': 'index.html', 'diff': '-old\n+new'},
    ],
  };
  @override
  Future<Map<String, dynamic>> builderModels() async => {
    'models': ['test-codex'],
  };
  @override
  Future<List<Map<String, dynamic>>> builderProjects() async => [];
  @override
  Future<List<Map<String, dynamic>>> codingRepositories() async => [
    {'full_name': 'owner/demo'},
  ];
  @override
  Future<List<Map<String, dynamic>>> codingDrafts() async => [draft];
  @override
  Future<Map<String, dynamic>> codingDetail(String id) async => draft;
  @override
  Future<Map<String, dynamic>> codingAction(String id, String action, Map<String, dynamic> body) async {
    if (action == 'publish') published++;
    return draft;
  }

  @override
  Future<Map<String, dynamic>> codingCreate(Map<String, dynamic> data) async {
    createdCalls++;
    created = data;
    return draft;
  }
}

void main() {
  conversationTests();
  temporaryContextTests();
  testWidgets('publishing requires a separate explicit confirmation after review', (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = CodingApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: const MaterialApp(home: CodingScreen()),
      ),
    );
    await tester.pumpAndSettle();
    expect(api.published, 0);
    expect(find.byType(DropdownButtonFormField<String>), findsNothing);
    await tester.ensureVisible(find.text('Existing task'));
    await tester.tap(find.text('Existing task'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Publish & run GitHub checks'));
    await tester.tap(find.text('Publish & run GitHub checks'));
    await tester.pumpAndSettle();
    expect(find.text('Publish reviewed files?'), findsOneWidget);
    expect(api.published, 0);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(api.published, 0);
    await tester.pumpWidget(const SizedBox.shrink());
    api.close();
  });
}

class OwnerAuth extends AuthController {
  @override
  Future<User?> build() async => const User(
    id: 'owner',
    email: 'owner@example.test',
    displayName: 'Owner',
    role: 'user',
    routingPolicy: 'balanced',
  );
}

class ChatCodingApi extends CodingApi {
  int contextReads = 0;
  @override
  Future<ConversationDetail> conversation(String id) async {
    contextReads++;
    return ConversationDetail(
      summary: ConversationSummary(id: id, title: 'Selected chat', pinned: false, updatedAt: DateTime.utc(2026)),
      messages: const [
        ChatMessage(
          id: 'note',
          role: 'user',
          content: 'Use CLI and CSV inputs. Keep IDs as text.',
          status: MessageStatus.complete,
        ),
      ],
    );
  }
}

void conversationTests() {
  testWidgets('chat questions replace dropdowns and generation receives the selected chat and answers', (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = ChatCodingApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api), authControllerProvider.overrideWith(OwnerAuth.new)],
        child: MaterialApp(
          home: Consumer(
            builder: (context, ref, _) {
              final user = ref.watch(authControllerProvider);
              if (!user.hasValue) return const SizedBox.shrink();
              return CodingScreen(
                seed: {
                  'user_id': 'owner',
                  'server': api.baseUrl,
                  'conversation_id': 'selected',
                  'task': 'Create a Python agent',
                },
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(api.contextReads, 1);
    expect(find.byType(DropdownButtonFormField<String>), findsNothing);
    expect(api.created, isNull);
    for (final label in [
      'Create a new project',
      'Use the details already provided',
      'Keep this project private',
      'test-codex',
      'No automatic repair (recommended)',
    ]) {
      await tester.ensureVisible(find.text(label).last);
      await tester.tap(find.text(label).last);
      await tester.pumpAndSettle();
    }
    await tester.ensureVisible(find.text('Start coding'));
    await tester.tap(find.text('Start coding'));
    await tester.pumpAndSettle();
    expect(api.created?['instructions'], contains('Use CLI and CSV inputs'));
    expect(api.created?['instructions'], contains('Create a Python agent'));
    expect(api.created?['runtime'], 'python');
    expect(api.created?['auto_repair'], isFalse);
    await tester.ensureVisible(find.text('Start coding'));
    await tester.tap(find.text('Start coding'));
    await tester.pumpAndSettle();
    expect(api.createdCalls, 1);
    expect(api.published, 0);
    await tester.pumpWidget(const SizedBox.shrink());
    api.close();
  });

  testWidgets('context from another account is not rendered or requested', (tester) async {
    final api = ChatCodingApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api), authControllerProvider.overrideWith(OwnerAuth.new)],
        child: MaterialApp(
          home: Consumer(
            builder: (context, ref, _) {
              final user = ref.watch(authControllerProvider);
              if (!user.hasValue) return const SizedBox.shrink();
              return CodingScreen(
                seed: {
                  'user_id': 'different-owner',
                  'server': api.baseUrl,
                  'conversation_id': 'private',
                  'task': 'Secret task from another account',
                },
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(api.contextReads, 0);
    expect(find.text('Secret task from another account'), findsNothing);
    expect(api.created, isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    api.close();
  });
}

void temporaryContextTests() {
  testWidgets('temporary chat history is not fetched even when a conversation ID is supplied', (tester) async {
    final api = ChatCodingApi();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api), authControllerProvider.overrideWith(OwnerAuth.new)],
        child: MaterialApp(
          home: Consumer(
            builder: (context, ref, _) {
              if (!ref.watch(authControllerProvider).hasValue) return const SizedBox.shrink();
              return CodingScreen(
                seed: {
                  'user_id': 'owner',
                  'server': api.baseUrl,
                  'conversation_id': 'temporary-chat',
                  'temporary': true,
                  'task': 'Create a Python CLI',
                },
              );
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(api.contextReads, 0);
    expect(find.text('Create a Python CLI'), findsOneWidget);
    expect(api.created, isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    api.close();
  });
}
