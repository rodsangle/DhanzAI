import 'dart:typed_data';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/folder_types.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/operations/operations_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class OperationsApi extends ApiClient {
  OperationsApi()
    : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  final List<Map<String, dynamic>> grants = [];
  final List<Map<String, dynamic>> writes = [];
  @override
  Future<Map<String, dynamic>> operations() async => {
    'servers': [
      {
        'id': 'server-one',
        'name': 'AWS test',
        'revoked': false,
        'last_seen': 'now',
        'tasks': [
          {'name': 'health', 'description': 'Check readiness; no changes'},
        ],
      },
    ],
    'grants': grants,
    'jobs': <Map<String, dynamic>>[],
  };
  @override
  Future<Map<String, dynamic>> operationAction(
    String path,
    Map<String, dynamic> body,
  ) async {
    writes.add({'path': path, ...body});
    return {};
  }
}

void main() {
  test(
    'folder review excludes private/generated paths before reading any bytes',
    () {
      var reads = 0;
      FolderFile file(String path) => FolderFile(path, 3, () async {
        reads++;
        return Uint8List(3);
      });
      final result = checkedFolderFiles([
        file('project/src/main.py'),
        file('project/docs/main.py'),
        file('project/.env'),
        file('project/.aws/credentials'),
        file('project/node_modules/pkg.js'),
        file('project/private.pem'),
      ]);
      expect(result.map((f) => f.path), [
        'project/src/main.py',
        'project/docs/main.py',
      ]);
      expect(reads, 0);
      expect(
        () => checkedFolderFiles([file('../escape.txt')]),
        throwsFormatException,
      );
      expect(
        () => checkedFolderFiles([file('same.txt'), file('same.txt')]),
        throwsFormatException,
      );
      expect(
        () => checkedFolderFiles(
          List.generate(201, (i) => file('project/$i.txt')),
        ),
        throwsFormatException,
      );
    },
  );

  testWidgets(
    'standing permission names the exact task and needs one explicit setup authorization',
    (tester) async {
      final api = OperationsApi();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [apiClientProvider.overrideWithValue(api)],
          child: const MaterialApp(home: OperationsScreen()),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('Authorize').first);
      await tester.tap(find.text('Authorize').first);
      await tester.pumpAndSettle();
      expect(api.writes, isEmpty);
      expect(
        find.textContaining('10 executions over the next 24 hours'),
        findsOneWidget,
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Authorize'));
      await tester.pumpAndSettle();
      expect(api.writes.single, {
        'path': 'grants',
        'kind': 'server_task',
        'target': 'server-one',
        'task': 'health',
        'hours': 24,
        'uses': 10,
        'authorize': true,
      });
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
