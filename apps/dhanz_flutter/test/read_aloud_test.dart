import 'dart:async';

import 'package:dhanz_ai/features/chat/reply_reader.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeReplySpeech implements ReplySpeech {
  final spoken = <String>[];
  Completer<void>? pending;
  bool fail = false;

  @override
  Future<void> speak(String text) {
    if (fail) return Future.error(StateError('Unavailable'));
    spoken.add(text);
    pending = Completer<void>();
    return pending!.future;
  }

  @override
  Future<void> stop() async {
    finish();
  }

  void finish() {
    final current = pending;
    pending = null;
    if (current != null && !current.isCompleted) current.complete();
  }
}

void main() {
  test('prose keeps long content and readable link labels', () {
    final text = replySpeechText('# Hello **world**\n[Docs](https://example.com)\n```js\nsecret code\n```');
    expect(text, contains('Hello world Docs'));
    expect(text, isNot(contains('https://')));
    expect(text, isNot(contains('secret code')));
    final words = List.generate(1200, (i) => 'word$i').join(' ');
    final chunks = replySpeechChunks(words);
    expect(chunks.length, greaterThan(1));
    expect(chunks.every((c) => c.length <= 1000), isTrue);
    expect(chunks.join(' '), words);
  });

  test('switching replies cancels the previous reply without clearing the new one', () async {
    final speech = FakeReplySpeech();
    final reader = ReplyReader(speech);
    final first = Object();
    final second = Object();
    final firstRun = reader.toggle(first, 'First reply');
    await Future<void>.delayed(Duration.zero);
    expect(reader.isReading(first), isTrue);
    final secondRun = reader.toggle(second, 'Second reply');
    await Future<void>.delayed(Duration.zero);
    await firstRun;
    expect(reader.isReading(second), isTrue);
    expect(speech.spoken, ['First reply', 'Second reply']);
    await reader.stop(second);
    await secondRun;
    expect(reader.isReading(second), isFalse);
    reader.dispose();
  });

  testWidgets('read button becomes Stop and a second click stops speech', (tester) async {
    final speech = FakeReplySpeech();
    final reader = ReplyReader(speech);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReadAloudButton(text: 'Hello', reader: reader),
        ),
      ),
    );
    await tester.tap(find.byTooltip('Read aloud'));
    await tester.pump();
    expect(find.byTooltip('Stop reading'), findsOneWidget);
    expect(speech.spoken, ['Hello']);
    await tester.tap(find.byTooltip('Stop reading'));
    await tester.pump();
    expect(find.byTooltip('Read aloud'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    reader.dispose();
  });

  testWidgets('removing the message stops speech', (tester) async {
    final speech = FakeReplySpeech();
    final reader = ReplyReader(speech);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReadAloudButton(text: 'Hello', reader: reader),
        ),
      ),
    );
    await tester.tap(find.byTooltip('Read aloud'));
    await tester.pump();
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    expect(speech.pending, isNull);
    reader.dispose();
  });

  testWidgets('speech errors explain availability and allow retry', (tester) async {
    final speech = FakeReplySpeech()..fail = true;
    final reader = ReplyReader(speech);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ReadAloudButton(text: 'Hello', reader: reader),
        ),
      ),
    );
    await tester.tap(find.byTooltip('Read aloud'));
    await tester.pump();
    expect(find.textContaining('Read aloud is unavailable'), findsOneWidget);
    expect(find.byTooltip('Read aloud'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    reader.dispose();
  });
}
