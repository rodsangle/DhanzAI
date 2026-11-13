import 'dart:async';

import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/voice/audio_io.dart';
import 'package:dhanz_ai/features/voice/read_aloud_button.dart';
import 'package:dhanz_ai/features/voice/voice_controller.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class TestSpeaker implements VoiceSpeaker {
  final spoken = <String>[];
  Completer<void>? pending;

  @override
  Future<List<String>> voices() async => [];
  @override
  Future<void> configure({String? voice, double rate = 0.5}) async {}
  @override
  Future<void> speak(String text) {
    spoken.add(text);
    pending = Completer<void>();
    return pending!.future;
  }

  @override
  Future<void> stop() async {
    final current = pending;
    pending = null;
    if (current != null && !current.isCompleted) current.complete();
  }
}

void main() {
  testWidgets('existing reader exposes start and stop on a completed reply', (tester) async {
    final speaker = TestSpeaker();
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          voiceSpeakerProvider.overrideWithValue(speaker),
          secureStoreProvider.overrideWithValue(MemorySecureStore()),
        ],
        child: const MaterialApp(
          home: Scaffold(body: ReadAloudButton(text: 'Hello from Dhanz')),
        ),
      ),
    );
    await tester.tap(find.byTooltip('Read aloud'));
    await tester.pump();
    expect(speaker.spoken, ['Hello from Dhanz']);
    expect(find.byTooltip('Stop reading'), findsOneWidget);
    await tester.tap(find.byTooltip('Stop reading'));
    await tester.pump();
    expect(find.byTooltip('Read aloud'), findsOneWidget);
    expect(speaker.pending, isNull);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });

  test('switching speech owner stops the old reply and retains the new owner', () async {
    final speaker = TestSpeaker();
    final container = ProviderContainer(
      overrides: [
        voiceSpeakerProvider.overrideWithValue(speaker),
        secureStoreProvider.overrideWithValue(MemorySecureStore()),
      ],
    );
    final controller = container.read(readAloudProvider.notifier);
    final first = controller.read('first', 'First reply');
    await Future<void>.delayed(Duration.zero);
    final second = controller.read('second', 'Second reply');
    await Future<void>.delayed(Duration.zero);
    await first;
    expect(container.read(readAloudProvider), 'second');
    expect(speaker.spoken, ['First reply', 'Second reply']);
    await controller.stop('second');
    await second;
    expect(container.read(readAloudProvider), isNull);
    container.dispose();
  });
}
