import 'dart:async';
import 'dart:typed_data';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/features/memory/memory_screen.dart';
import 'package:dhanz_ai/features/projects/projects_controller.dart';
import 'package:dhanz_ai/features/voice/audio_io.dart';
import 'package:dhanz_ai/features/voice/voice_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

class FakeRecorder implements VoiceRecorder {
  final levelsController = StreamController<double>.broadcast();
  bool permitted = true;
  bool recording = false;
  int starts = 0;

  @override
  Future<bool> hasPermission() async => permitted;

  @override
  Future<void> start() async {
    recording = true;
    starts++;
  }

  @override
  Stream<double> levels() => levelsController.stream;

  @override
  Future<Recording?> stop() async {
    recording = false;
    return (bytes: Uint8List.fromList([1, 2, 3]), filename: 'speech.m4a');
  }

  @override
  Future<void> cancel() async => recording = false;

  @override
  Future<void> dispose() async {}
}

class FakeSpeaker implements VoiceSpeaker {
  final spoken = <String>[];

  @override
  Future<void> configure({String? voice, double rate = 0.5}) async {}

  @override
  Future<void> speak(String text) async => spoken.add(text);

  @override
  Future<void> stop() async {}

  @override
  Future<List<String>> voices() async => const ['Ava|en-US'];
}

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;
  late FakeRecorder recorder;
  late FakeSpeaker speaker;

  List<Override> overrides() => [
    secureStoreProvider.overrideWithValue(store),
    apiClientProvider.overrideWith(
      (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
    ),
    voiceRecorderProvider.overrideWithValue(recorder),
    voiceSpeakerProvider.overrideWithValue(speaker),
  ];

  setUp(() async {
    backend = FakeBackend()..reply = 'Paris is the **capital** of France [1].';
    store = MemorySecureStore();
    recorder = FakeRecorder();
    speaker = FakeSpeaker();
    await ApiClient(
      store: store,
      baseUrl: 'http://test',
      clientFactory: backend.client,
    ).register('ada@example.com', 'correct-horse-9', 'Ada');
  });

  Future<ProviderContainer> container() async {
    final c = ProviderContainer(overrides: overrides());
    addTearDown(c.dispose);
    await c.read(authControllerProvider.future);
    return c;
  }

  group('voice', () {
    test('wake phrase and speech cleanup helpers', () {
      expect(stripWakePhrase('Hey Dhanz, search for chips'), 'search for chips');
      expect(stripWakePhrase('ok dhanz what time is it?'), 'what time is it?');
      expect(stripWakePhrase('search for chips'), isNull);
      expect(
        toSpeech('## Result\n**Paris** is the capital [1].\n```python\nprint(1)\n```\n- see [docs](https://x.y)'),
        'Result Paris is the capital . (I have put the code on screen.) see docs',
      );
    });

    test('listen → end of speech → transcribe → ask → speak', () async {
      final c = await container();
      final voice = c.read(voiceControllerProvider.notifier);
      await voice.listen();
      expect(recorder.recording, isTrue);
      expect(c.read(voiceControllerProvider).phase, VoicePhase.listening);

      // Speech, then silence long enough to end the utterance.
      recorder.levelsController.add(-20);
      await Future<void>.delayed(const Duration(milliseconds: 10));
      recorder.levelsController.add(-70);
      await Future<void>.delayed(Vad.endOfSpeech + const Duration(milliseconds: 100));
      recorder.levelsController.add(-70);
      await pumpEventQueue(times: 50);

      final state = c.read(voiceControllerProvider);
      expect(backend.requests, contains('POST /voice/transcribe'));
      expect(state.transcript, 'Hey Dhanz, what is the capital of France?');
      expect(speaker.spoken.single, 'Paris is the capital of France .');
      expect(state.phase, VoicePhase.idle);
      expect(c.read(chatControllerProvider).messages.last.content, backend.reply);
    });

    test('wake phrase required: other speech is ignored', () async {
      final c = await container();
      final voice = c.read(voiceControllerProvider.notifier)..setWakePhrase(true);
      await voice.handleTranscript('what is the capital of France?');
      expect(c.read(voiceControllerProvider).status, contains('Hey Dhanz'));
      expect(backend.chatBodies, isEmpty);
      await voice.handleTranscript('Hey Dhanz, what is the capital of France?');
      expect(backend.chatBodies.single['content'], 'what is the capital of France?');
    });

    test('hands-free listens again after answering; stop ends it', () async {
      final c = await container();
      final voice = c.read(voiceControllerProvider.notifier)..setHandsFree(true);
      await voice.handleTranscript('Tell me a fact');
      expect(speaker.spoken, hasLength(1));
      expect(recorder.recording, isTrue);
      await voice.stop();
      expect(recorder.recording, isFalse);
      expect(c.read(voiceControllerProvider).handsFree, isFalse);
    });

    test('microphone permission denied is explained', () async {
      final c = await container();
      recorder.permitted = false;
      await c.read(voiceControllerProvider.notifier).listen();
      expect(c.read(voiceControllerProvider).error, contains('Microphone access was denied'));
    });
  });

  group('attachments, projects and memory', () {
    test('uploaded files are attached to the next message, inside the selected project', () async {
      final c = await container();
      final project = await c.read(apiClientProvider).createProject('Plant A');
      c.read(selectedProjectProvider.notifier).select(project.id);
      final chat = c.read(chatControllerProvider.notifier);

      await chat.attachFile('report.pdf', Uint8List.fromList([37, 80, 68, 70]));
      expect(c.read(chatControllerProvider).attachments.single.title, 'report.pdf');
      expect(backend.uploads.single, contains('name="project_id"'));

      await chat.send('Summarize this report');
      expect(backend.conversationBodies.single['project_id'], project.id);
      expect(backend.chatBodies.single['attachment_ids'], [backend.documents.single['id']]);
      final state = c.read(chatControllerProvider);
      expect(state.attachments, isEmpty);
      expect(state.messages.first.attachments.single.filename, 'report.pdf');
    });

    test('"remember that" produces a notice', () async {
      final c = await container();
      await c.read(chatControllerProvider.notifier).send('Remember that I prefer metric units.');
      expect(c.read(chatControllerProvider).notice, contains('I prefer metric units'));
    });

    testWidgets('memory screen: turn memory on and add a memory', (tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
      await tester.pumpAndSettle();
      final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
      container.read(routerProvider).go('/memory');
      await tester.pumpAndSettle();

      expect(find.text('Nothing saved yet.'), findsOneWidget);
      await tester.tap(find.byType(Switch));
      await tester.pumpAndSettle();
      expect(backend.requests, contains('PATCH /users/me'));
      expect(tester.widget<Switch>(find.byType(Switch)).value, isTrue);

      await tester.tap(find.text('Add memory'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).last, 'Call me Ada');
      await tester.tap(find.widgetWithText(FilledButton, 'Remember'));
      await tester.pumpAndSettle();
      expect(find.text('Call me Ada'), findsOneWidget);
      expect(container.read(memoriesProvider).value, hasLength(1));
    });

    testWidgets('projects and voice screens render and work', (tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
      await tester.pumpAndSettle();
      final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));

      container.read(routerProvider).go('/projects');
      await tester.pumpAndSettle();
      expect(find.text('No projects yet'), findsOneWidget);
      await tester.tap(find.text('New project'));
      await tester.pumpAndSettle();
      await tester.enterText(find.widgetWithText(TextField, 'Name'), 'Plant A');
      await tester.tap(find.widgetWithText(FilledButton, 'Save'));
      await tester.pumpAndSettle();
      expect(find.text('Plant A'), findsOneWidget);
      expect(container.read(selectedProjectProvider), backend.projects.single['id']);

      container.read(routerProvider).go('/voice');
      await tester.pumpAndSettle();
      expect(find.text('Tap the microphone and speak'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Start talking'));
      await tester.pump();
      expect(recorder.recording, isTrue);
      expect(find.text('Listening…'), findsOneWidget);
      container.read(routerProvider).go('/chat'); // leaving the screen releases the microphone
      await tester.pumpAndSettle();
      expect(recorder.recording, isFalse);
    });
  });
}
