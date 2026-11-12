@TestOn('browser')
library;

import 'dart:js_interop';
import 'package:flutter_test/flutter_test.dart';
import 'package:dhanz_ai/features/voice/wake_web.dart';

@JS('eval')
external JSAny? evaluate(JSString source);

void main() {
  test('browser wake adapter forwards final text and detaches callbacks on stop', () {
    evaluate('''
      globalThis.__dhanzPreviousRecognition = globalThis.SpeechRecognition;
      globalThis.SpeechRecognition = class {
        constructor() { globalThis.__dhanzTestRecognition = this; }
        start() { this.started = true; }
        abort() { this.aborted = true; }
      };
    '''.toJS);
    final recognizer = createWakeRecognizer();
    final texts = <String>[];
    try {
      expect(recognizer.supported, isTrue);
      recognizer.start(onText: texts.add, onError: (message) => fail(message), onEnd: () {});
      evaluate('''
        globalThis.__dhanzTestRecognition.onresult({resultIndex: 0, results: [
          {isFinal: false, item: () => ({transcript: 'interim'})},
          {isFinal: true, item: () => ({transcript: 'Hey Dhanz, hello'})}
        ]});
      '''.toJS);
      expect(texts, ['Hey Dhanz, hello']);
      recognizer.stop();
      final stopped = evaluate('globalThis.__dhanzTestRecognition.aborted && globalThis.__dhanzTestRecognition.onresult === null'.toJS) as JSBoolean;
      expect(stopped.toDart, isTrue);
    } finally {
      recognizer.stop();
      evaluate('globalThis.SpeechRecognition = globalThis.__dhanzPreviousRecognition; delete globalThis.__dhanzTestRecognition; delete globalThis.__dhanzPreviousRecognition;'.toJS);
    }
  });
}
