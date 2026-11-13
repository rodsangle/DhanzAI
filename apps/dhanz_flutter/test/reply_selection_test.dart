import 'dart:ui';

import 'package:dhanz_ai/features/chat/markdown_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('mouse drag selects across Markdown paragraphs and copy preserves selected text', (tester) async {
    String copied = '';
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String;
      }
      if (call.method == 'Clipboard.getData') return {'text': copied};
      return null;
    });
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Padding(
            padding: EdgeInsets.all(24),
            child: MarkdownView(
              'First paragraph for selection.\n\nSecond paragraph for selection.\n\n```python\nprint("hello")\n```',
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final first = find.text('First paragraph for selection.', findRichText: true).first;
    final second = find.text('Second paragraph for selection.', findRichText: true).first;
    final start = tester.getTopLeft(first) + const Offset(1, 8);
    final end = tester.getBottomRight(second) - const Offset(1, 8);
    final gesture = await tester.startGesture(start, kind: PointerDeviceKind.mouse);
    await gesture.moveTo(end);
    await gesture.up();
    await tester.pumpAndSettle();
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyC);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pump();
    expect(copied, contains('First paragraph'));
    expect(copied, contains('Second paragraph'));
    expect(find.byType(SelectionArea), findsOneWidget);
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null);
  });
}
