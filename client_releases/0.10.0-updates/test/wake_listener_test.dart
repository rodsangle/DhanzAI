import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/voice/audio_io.dart';
import 'package:dhanz_ai/features/voice/voice_controller.dart';
import 'package:dhanz_ai/features/voice/wake_listener.dart';
import 'package:dhanz_ai/features/voice/wake_types.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeWake implements WakeRecognizer {
  int starts = 0, stops = 0;
  void Function(String)? text;
  void Function(String)? error;
  @override
  bool get supported => true;
  @override
  void start({required void Function(String) onText, required void Function(String) onError, required void Function() onEnd}) { starts++; text = onText; error = onError; }
  @override
  void stop() { stops++; text = null; error = null; }
}
class QuietSpeaker implements VoiceSpeaker {
  @override
  Future<List<String>> voices() async => [];
  @override
  Future<void> configure({String? voice, double rate = 0.5}) async {}
  @override
  Future<void> speak(String text) async {}
  @override
  Future<void> stop() async {}
}
void main() {
  test('wake phrase requires Dhanz and preserves the requested action', () {
    expect(stripWakePhrase('Hey Dhanz, what is the weather?'), 'what is the weather?');
    expect(stripWakePhrase('open a site'), isNull);
    expect(stripWakePhrase('Hey Dhanz'), '');
  });
  testWidgets('wake listening requires consent and stops on app hide and disposal', (tester) async {
    final wake = FakeWake();
    await tester.pumpWidget(ProviderScope(overrides: [wakeRecognizerProvider.overrideWithValue(wake), voiceSpeakerProvider.overrideWithValue(QuietSpeaker()), secureStoreProvider.overrideWithValue(MemorySecureStore())], child: const MaterialApp(home: Scaffold(body: WakeListener()))));
    expect(wake.starts, 0);
    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();
    expect(find.text('Enable “Hey Dhanz”?'), findsOneWidget);
    expect(wake.starts, 0);
    await tester.tap(find.text('Enable microphone'));
    await tester.pumpAndSettle();
    expect(wake.starts, 1);
    wake.error!('no-speech');
    await tester.pump();
    expect(tester.widget<Switch>(find.byType(Switch)).value, isTrue, reason: 'Normal recognition silence must not disable wake listening');
    wake.text!('this is unrelated speech');
    await tester.pump();
    expect(find.text('Listening for “Hey Dhanz”…'), findsOneWidget);
    wake.text!('Hey Dhanz');
    await tester.pump();
    expect(find.text('Yes? Say your request within 10 seconds.'), findsOneWidget);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
    await tester.pump();
    expect(wake.text, isNull, reason: 'Microphone callbacks must detach immediately while hidden');
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(tester.widget<Switch>(find.byType(Switch)).value, isFalse);
    expect(wake.starts, 1, reason: 'Returning to the foreground must not silently reopen the mic');
    await tester.pumpWidget(const SizedBox());
    expect(wake.text, isNull);
  });
}
