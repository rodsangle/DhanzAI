import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:dhanz_ai/features/chat/chat_preview.dart';

void main() {
  Future<void> app(
    WidgetTester tester,
    ChatPreviewController controller, {
    double width = 1400,
  }) async {
    tester.view.physicalSize = Size(width, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ChatPreviewHost(
            controller: controller,
            previewBuilder: (_, target) => Column(
              children: [
                Text('Content: ${target.documentId}'),
                const TextField(),
              ],
            ),
            child: Builder(
              builder: (context) => Center(
                child: FilledButton(
                  onPressed: () => ChatPreviewScope.of(context)!.open(
                    const ChatPreviewTarget(
                      documentId: 'one',
                      filename: 'Test.xlsx',
                    ),
                  ),
                  child: const Text('Preview file'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  testWidgets(
    'starts closed, opens only on Preview, closes with X and reopens',
    (tester) async {
      final controller = ChatPreviewController();
      addTearDown(controller.dispose);
      await app(tester, controller);
      expect(find.byKey(const ValueKey('chat-preview-panel')), findsNothing);
      await tester.tap(find.text('Preview file'));
      await tester.pump();
      expect(find.text('Content: one'), findsOneWidget);
      expect(
        tester.getTopLeft(find.byKey(const ValueKey('chat-preview-panel'))).dx,
        greaterThan(500),
      );
      await tester.tap(find.byTooltip('Close preview'));
      await tester.pump();
      expect(find.text('Content: one'), findsNothing);
      await tester.tap(find.text('Preview file'));
      await tester.pump();
      expect(find.text('Content: one'), findsOneWidget);
      await tester.sendKeyEvent(LogicalKeyboardKey.escape);
      await tester.pump();
      expect(find.byKey(const ValueKey('chat-preview-panel')), findsNothing);
    },
  );

  testWidgets(
    'drags wider, expands and restores without losing preview state',
    (tester) async {
      final controller = ChatPreviewController();
      addTearDown(controller.dispose);
      await app(tester, controller);
      await tester.tap(find.text('Preview file'));
      await tester.pump();
      final before = tester
          .getSize(find.byKey(const ValueKey('preview-width')))
          .width;
      await tester.drag(
        find.byKey(const ValueKey('preview-resize-handle')),
        const Offset(-130, 0),
      );
      await tester.pump();
      expect(
        tester.getSize(find.byKey(const ValueKey('preview-width'))).width,
        greaterThan(before),
      );
      await tester.enterText(find.byType(TextField), 'Keep selection');
      await tester.tap(find.byTooltip('Expand preview'));
      await tester.pump();
      expect(find.text('Keep selection'), findsOneWidget);
      expect(
        tester.getSize(find.byKey(const ValueKey('chat-preview-panel'))).width,
        1400,
      );
      await tester.tap(find.byTooltip('Restore preview size'));
      await tester.pump();
      expect(find.text('Keep selection'), findsOneWidget);
      expect(
        find.byKey(const ValueKey('preview-resize-handle')),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('phone fits, switches files and clears previous conversation', (
    tester,
  ) async {
    final controller = ChatPreviewController();
    addTearDown(controller.dispose);
    await app(tester, controller, width: 390);
    await tester.tap(find.text('Preview file'));
    await tester.pump();
    expect(
      tester.getSize(find.byKey(const ValueKey('chat-preview-panel'))).width,
      390,
    );
    controller.open(
      const ChatPreviewTarget(documentId: 'two', filename: 'Other.xlsx'),
    );
    await tester.pump();
    expect(find.text('Content: one'), findsNothing);
    expect(find.text('Content: two'), findsOneWidget);
    controller.clear();
    await tester.pump();
    expect(controller.target, isNull);
    expect(find.byKey(const ValueKey('chat-preview-panel')), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
