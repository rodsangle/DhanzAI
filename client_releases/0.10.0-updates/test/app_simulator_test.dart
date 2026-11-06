import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:dhanz_ai/features/builder/app_simulator.dart';
import 'package:dhanz_ai/features/builder/preview_document.dart';

void main() {
  test('mobile companion resolves its local assets and retains isolation policy', () {
    final html = previewDocument([
      {'path': 'simulator/index.html', 'content': '<script src="app.js"></script><link href="style.css" rel="stylesheet">'},
      {'path': 'simulator/app.js', 'content': 'let locked = true;'},
      {'path': 'simulator/style.css', 'content': 'button {color:green;}'},
    ], entryPath: 'simulator/index.html');
    expect(html, contains('let locked = true'));
    expect(html, contains('button {color:green;}'));
    expect(html, contains("connect-src 'none'"));
    expect(html, contains("form-action 'none'"));
  });

  testWidgets('simulator queues a revised copy and shows pending state', (tester) async {
    final source = <String, dynamic>{'id': 'one', 'name': 'Vehicle demo', 'kind': 'app',
      'status': 'complete', 'files': <Map<String,dynamic>>[
        {'path': 'simulator/index.html', 'content': '<button>Lock</button>'}]};
    final revised = <String, dynamic>{'id': 'two', 'name': 'Vehicle revised', 'kind': 'app', 'status': 'queued'};
    final calls = <String>[];
    await tester.pumpWidget(MaterialApp(home: Scaffold(body: AppSimulatorPanel(
      initialProjectId: 'one', listProjects: () async => [source], loadProject: (_) async => source,
      downloadProject: (_) async => Uint8List(0), reviseProject: (id, changes, key) async {
        calls.add('$id:$changes');
        expect(key.length, greaterThan(16));
        return revised;
      }))));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'Simulator widget must render without a layout exception');
    expect(find.text('Browser demo · simulated integrations'), findsOneWidget);
    expect(find.byTooltip('Reset simulator'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'Make the lock button larger');
    await tester.tap(find.text('Update app & simulator'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull, reason: 'Simulator widget must render without a layout exception');
    expect(calls, ['one:Make the lock button larger']);
    expect(find.textContaining('Building source and simulator'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
}
