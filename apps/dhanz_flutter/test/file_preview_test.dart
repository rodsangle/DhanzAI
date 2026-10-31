import 'dart:convert';
import 'dart:async';
import 'dart:typed_data';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/chat/attachment_chip.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:file_picker/file_picker.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('preview opens without downloading and switches sections', (tester) async {
    final requests = <String>[];
    final api = ApiClient(
      store: MemorySecureStore(),
      baseUrl: 'http://test',
      clientFactory: () => MockClient((request) async {
        requests.add(request.url.path);
        return http.Response(
          jsonEncode({
            'sections': [
              {
                'title': 'Budget',
                'rows': [
                  ['Item', 'Cost'],
                  ['Rent', '100'],
                ],
              },
              {'title': 'Notes', 'text': 'Second sheet notes'},
            ],
            'truncated': true,
          }),
          200,
        );
      }),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [apiClientProvider.overrideWithValue(api)],
        child: const MaterialApp(
          home: Scaffold(
            body: AttachmentChip(documentId: 'abc', filename: 'Budget.xlsx', previewEnabled: true),
          ),
        ),
      ),
    );
    await tester.tap(find.text('Preview'));
    await tester.pumpAndSettle();
    expect(find.text('Rent'), findsOneWidget);
    expect(find.text('Download'), findsNWidgets(2));
    expect(find.textContaining('Preview shortened'), findsOneWidget);
    await tester.tap(find.text('Notes'));
    await tester.pumpAndSettle();
    expect(find.text('Second sheet notes'), findsOneWidget);
    expect(requests, ['/api/v1/files/abc/preview']);
    await tester.tap(find.byTooltip('Close preview'));
    await tester.pumpAndSettle();
    expect(find.text('Second sheet notes'), findsNothing);
  });

  for (final outcome in ['saved', 'cancelled', 'failed']) {
    testWidgets('Download fetches the file and reports $outcome', (tester) async {
      final original = FilePickerPlatform.instance;
      final picker = _SavePicker();
      FilePickerPlatform.instance = picker;
      addTearDown(() => FilePickerPlatform.instance = original);
      final requests = <String>[];
      final api = ApiClient(
        store: MemorySecureStore(),
        baseUrl: 'http://test',
        clientFactory: () => MockClient((request) async {
          requests.add(request.url.path);
          return http.Response.bytes([1, 2, 3], 200);
        }),
      );
      await tester.pumpWidget(
        ProviderScope(
          overrides: [apiClientProvider.overrideWithValue(api)],
          child: const MaterialApp(
            home: Scaffold(
              body: AttachmentChip(documentId: 'abc', filename: 'Budget.xlsx'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('Download'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));
      expect(find.text('Downloading…'), findsOneWidget);
      expect(requests, ['/api/v1/files/abc/download']);
      expect(picker.filename, 'Budget.xlsx');
      expect(picker.bytes, [1, 2, 3]);
      expect(picker.mime, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
      if (outcome == 'failed') {
        picker.result.completeError(Exception('Save picker failed'));
      } else {
        picker.result.complete(outcome == 'saved' ? Uri.parse('content://downloads/Budget.xlsx') : null);
      }
      await tester.pumpAndSettle();
      expect(find.text('Download'), findsOneWidget);
      expect(
        find.textContaining(switch (outcome) {
          'saved' => 'Saved Budget.xlsx',
          'cancelled' => 'Download cancelled',
          _ => 'Could not save the file',
        }),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    });
  }
}

class _SavePicker extends FilePickerPlatform {
  final result = Completer<Uri?>();
  String? filename;
  String? mime;
  Uint8List? bytes;
  @override
  Future<Uri?> saveFile({
    required String fileName,
    required Uint8List bytes,
    required String mimeType,
    String? dialogTitle,
    String? initialDirectory,
    Function(FilePickerStatus)? onFileSaving,
    WindowsOptions windowsOptions = const WindowsOptions(),
    LinuxOptions linuxOptions = const LinuxOptions(),
    WebOptions webOptions = const WebOptions(),
  }) {
    filename = fileName;
    mime = mimeType;
    this.bytes = bytes;
    return result.future;
  }
}
