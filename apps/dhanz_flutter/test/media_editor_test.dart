import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/media_editor/media_editor_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class MediaApi extends ApiClient {
  MediaApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  @override
  Future<List<Map<String, dynamic>>> mediaJobs() async => [
    {'id': 'one', 'mode': 'video', 'status': 'running', 'source_name': 'clip.mp4'},
  ];
}

void main() {
  testWidgets('media editor shows durable jobs and rejects video exports without source', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(MediaApi())],
        child: const MaterialApp(home: MediaEditorScreen()),
      ),
    );
    await tester.pumpAndSettle();
    await tester.scrollUntilVisible(find.text('Create export'), 300, scrollable: find.byType(Scrollable).first);
    await tester.tap(find.text('Create export'));
    await tester.pumpAndSettle();
    expect(find.text('Choose a video first.'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('clip.mp4'), 200, scrollable: find.byType(Scrollable).first);
    expect(find.text('video · running'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
    await tester.pump();
    expect(tester.takeException(), isNull);
  });
}
