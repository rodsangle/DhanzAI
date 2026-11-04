import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/coding/coding_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class CodingApi extends ApiClient {
  CodingApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  int published = 0;
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
    created = data;
    return draft;
  }
}

void main() {
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
    expect(tester.widget<CheckboxListTile>(find.byType(CheckboxListTile)).value, isFalse);
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
