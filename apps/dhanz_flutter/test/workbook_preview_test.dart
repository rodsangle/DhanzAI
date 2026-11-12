import 'dart:typed_data';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/clipboard_images_types.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/chat/workbook_preview.dart';
import 'package:dhanz_ai/features/chat/chat_preview.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class WorkbookApi extends ApiClient {
  WorkbookApi() : super(store: MemorySecureStore(), baseUrl: 'https://example.test');
  final keys = <String>[];
  final edits = <List<Map<String, dynamic>>>[];
  bool fail = false;
  @override
  Future<Map<String, dynamic>> workbookPage(String id, {String? sheet, String area = 'A1:AN50'}) async => {
    'document_id': id,
    'filename': id == 'source' ? 'Source.xlsx' : 'Saved.xlsx',
    'sheet': 'Sheet',
    'sheets': ['Sheet'],
    'rows': 2,
    'columns': 2,
    'range': area,
    'cells': [
      {'cell': 'A1', 'value': 'ID', 'format': <String, dynamic>{}},
      {'cell': 'B1', 'value': 'Amount', 'format': <String, dynamic>{}},
      {'cell': 'A2', 'value': '0001', 'format': <String, dynamic>{}},
      {'cell': 'B2', 'value': 10, 'format': <String, dynamic>{}},
    ],
  };
  @override
  Future<Map<String, dynamic>> saveWorkbook(
    String id,
    String key,
    String filename,
    List<Map<String, dynamic>> actions,
  ) async {
    keys.add(key);
    edits.add(actions);
    if (fail) throw ApiException(503, 'Try again explicitly');
    return {'id': 'copy', 'filename': 'Saved.xlsx', 'original_preserved': true};
  }
}

void main() {
  Future<void> app(WidgetTester tester, WorkbookApi api) async {
    tester.view.physicalSize = const Size(1400, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: MaterialApp(
          home: Scaffold(
            body: WorkbookPreview(
              documentId: 'source',
              filename: 'Source.xlsx',
              downloadBuilder: (id, name) => Text('Download $id'),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Finder field(String label) => find.byWidgetPredicate((w) => w is TextField && w.decoration?.labelText == label);

  testWidgets('edits cells with leading zeros, supports undo and saves an actual copy', (tester) async {
    final api = WorkbookApi();
    await app(tester, api);
    await tester.enterText(field('Cell / range'), 'A2');
    await tester.enterText(field('Value or formula'), '0007');
    await tester.tap(find.byTooltip('Apply value or formula'));
    await tester.pump();
    expect(find.text('Save copy (1)'), findsOneWidget);
    expect(api.edits, isEmpty);
    await tester.tap(find.text('Undo'));
    await tester.pump();
    expect(find.text('Save copy (0)'), findsOneWidget);
    await tester.tap(find.text('Redo'));
    await tester.pump();
    await tester.tap(find.text('Save copy (1)'));
    await tester.pumpAndSettle();
    expect(api.edits.single.single['values'], [
      ['0007'],
    ]);
    expect(find.text('Download copy'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('uncertain save retries reuse the same key', (tester) async {
    final api = WorkbookApi()..fail = true;
    await app(tester, api);
    await tester.enterText(field('Cell / range'), 'B3');
    await tester.enterText(field('Value or formula'), '=SUM(B2:B2)');
    await tester.tap(find.byTooltip('Apply value or formula'));
    await tester.pump();
    await tester.tap(find.text('Save copy (1)'));
    await tester.pumpAndSettle();
    api.fail = false;
    await tester.tap(find.text('Save copy (1)'));
    await tester.pumpAndSettle();
    expect(api.keys.length, 2);
    expect(api.keys.first, api.keys.last);
    expect(api.edits.first.single['type'], 'set_formula');
  });

  testWidgets('closing warns about unsaved edits and saving updates the preview target', (tester) async {
    tester.view.physicalSize = const Size(1400, 1100);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final api = WorkbookApi();
    final controller = ChatPreviewController();
    addTearDown(controller.dispose);
    await controller.open(const ChatPreviewTarget(documentId: 'source', filename: 'Source.xlsx'));
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: ChatPreviewHost(
              controller: controller,
              child: const SizedBox(),
              previewBuilder: (_, target) => WorkbookPreview(
                documentId: target.documentId,
                filename: target.filename,
                downloadBuilder: (id, name) => Text('Download $id'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(Theme.of(tester.element(find.text('Workbook'))).brightness, Brightness.light);
    await tester.enterText(field('Cell / range'), 'B3');
    await tester.enterText(field('Value or formula'), '7');
    await tester.tap(find.byTooltip('Apply value or formula'));
    await tester.pump();
    await tester.tap(find.byTooltip('Close preview'));
    await tester.pumpAndSettle();
    expect(find.text('Discard unsaved changes?'), findsOneWidget);
    await tester.tap(find.text('Keep editing'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save copy (1)'));
    await tester.pumpAndSettle();
    expect(controller.target?.documentId, 'copy');
    await tester.tap(find.byTooltip('Close preview'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('chat-preview-panel')), findsNothing);
  });

  test('bounded ranges and clipboard image validation', () {
    expect(workbookRange('G33:AI33'), (7, 33, 35, 33));
    expect(workbookValue('0001'), '0001');
    expect(workbookValue('12345678901234567'), '12345678901234567');
    expect(workbookValue('10'), 10);
    expect(workbookValue('2.5'), 2.5);
    expect(
      workbookDisplay({
        'value': 0.5,
        'format': {'number_format': '0.00%'},
      }),
      '50.00%',
    );
    expect(() => workbookRange('A:AI'), throwsFormatException);
    ClipboardImageSource image(String mime, int size) =>
        ClipboardImageSource(name: 'clip.png', mime: mime, size: size, read: () async => Uint8List(1));
    validateClipboardImages([image('image/png', 100)]);
    expect(() => validateClipboardImages([image('image/svg+xml', 100)]), throwsStateError);
    expect(() => validateClipboardImages([image('image/png', 11 * 1024 * 1024)]), throwsStateError);
    expect(() => validateClipboardImages([]), throwsStateError);
  });
}
