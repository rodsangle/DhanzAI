import 'package:dhanz_ai/features/chat/draft_spelling.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('common English typos preserve case and whitespace', () {
    expect(
      suggestDraftSpelling('Teh messege\n  was RECIEVED wiht a reciept.'),
      'The message\n  was RECEIVED with a receipt.',
    );
    expect(suggestDraftSpelling('Please organise the colour catalogue.'), 'Please organise the colour catalogue.');
  });

  test('technical tokens and fenced code are protected', () {
    const input =
        'teh https://teh.example/recieve teh@example.com sk-proj-teh-token teh_id teh/main '
        '`teh inline`\n```python\nteh = "recieve"\n```\nrecieve';
    const expected =
        'the https://teh.example/recieve teh@example.com sk-proj-teh-token teh_id teh/main '
        '`teh inline`\n```python\nteh = "recieve"\n```\nreceive';
    expect(suggestDraftSpelling(input), expected);
    expect(suggestDraftSpelling('```\nteh'), '```\nteh');
  });

  test('raw structured input and common commands are protected', () {
    for (final text in ['{"teh": "recieve"}', '<div>teh</div>', 'curl https://example.com/teh', 'teh = "recieve"']) {
      expect(suggestDraftSpelling(text), text);
    }
  });

  Future<void> mount(WidgetTester tester, TextEditingController controller, {ValueChanged<bool>? onToggle}) =>
      tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: DraftSpellingButton(
              controller: controller,
              deviceAutocorrect: true,
              onDeviceAutocorrectChanged: onToggle ?? (_) {},
            ),
          ),
        ),
      );

  Future<void> review(WidgetTester tester) async {
    await tester.tap(find.byTooltip('Spelling options'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review spelling fixes'));
    await tester.pumpAndSettle();
  }

  testWidgets('device toggle does not rewrite or submit the draft', (tester) async {
    final controller = TextEditingController(text: 'teh messege');
    bool? enabled;
    await mount(tester, controller, onToggle: (value) => enabled = value);
    await tester.tap(find.byTooltip('Spelling options'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(CheckedPopupMenuItem<String>));
    await tester.pumpAndSettle();
    expect(enabled, isFalse);
    expect(controller.text, 'teh messege');
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });

  testWidgets('queued drafts can disable spelling controls', (tester) async {
    final controller = TextEditingController(text: 'teh messege');
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DraftSpellingButton(
            controller: controller,
            deviceAutocorrect: true,
            onDeviceAutocorrectChanged: (_) {},
            enabled: false,
          ),
        ),
      ),
    );
    expect(tester.widget<PopupMenuButton<String>>(find.byType(PopupMenuButton<String>)).enabled, isFalse);
    expect(controller.text, 'teh messege');
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });

  testWidgets('cancel preview preserves the original draft', (tester) async {
    final controller = TextEditingController(text: 'teh messege');
    await mount(tester, controller);
    await review(tester);
    expect(find.text('the message'), findsOneWidget);
    expect(controller.text, 'teh messege');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(controller.text, 'teh messege');
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });

  testWidgets('apply changes only the draft and offers undo', (tester) async {
    final controller = TextEditingController(text: 'teh messege');
    await mount(tester, controller);
    await review(tester);
    await tester.tap(find.text('Apply spelling fixes'));
    await tester.pumpAndSettle();
    expect(controller.text, 'the message');
    await tester.tap(find.text('Undo'));
    await tester.pumpAndSettle();
    expect(controller.text, 'teh messege');
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });

  testWidgets('a draft edited during review is not overwritten', (tester) async {
    final controller = TextEditingController(text: 'teh messege');
    await mount(tester, controller);
    await review(tester);
    controller.text = 'My newer draft';
    await tester.tap(find.text('Apply spelling fixes'));
    await tester.pumpAndSettle();
    expect(controller.text, 'My newer draft');
    expect(find.textContaining('Your draft changed'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    controller.dispose();
  });
}
