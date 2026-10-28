import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../core/storage/secure_store.dart';
import '../../models/models.dart';
import '../chat/chat_controller.dart';
import 'audio_io.dart';

enum VoicePhase { idle, listening, transcribing, thinking, speaking }

class VoiceState {
  const VoiceState({
    this.phase = VoicePhase.idle,
    this.transcript,
    this.reply,
    this.status,
    this.error,
    this.level = -160,
    this.handsFree = false,
    this.wakePhrase = false,
    this.voice,
    this.rate = 0.5,
    this.voices = const [],
  });

  final VoicePhase phase;
  final String? transcript;
  final String? reply;
  final String? status;
  final String? error;
  final double level;

  /// Keep the conversation going: listen again after each spoken reply.
  final bool handsFree;

  /// Only act on requests that start with "Hey Dhanz".
  final bool wakePhrase;
  final String? voice;
  final double rate;
  final List<String> voices;

  bool get busy => phase != VoicePhase.idle;

  VoiceState copyWith({
    VoicePhase? phase,
    String? Function()? transcript,
    String? Function()? reply,
    String? Function()? status,
    String? Function()? error,
    double? level,
    bool? handsFree,
    bool? wakePhrase,
    String? Function()? voice,
    double? rate,
    List<String>? voices,
  }) => VoiceState(
    phase: phase ?? this.phase,
    transcript: transcript != null ? transcript() : this.transcript,
    reply: reply != null ? reply() : this.reply,
    status: status != null ? status() : this.status,
    error: error != null ? error() : this.error,
    level: level ?? this.level,
    handsFree: handsFree ?? this.handsFree,
    wakePhrase: wakePhrase ?? this.wakePhrase,
    voice: voice != null ? voice() : this.voice,
    rate: rate ?? this.rate,
    voices: voices ?? this.voices,
  );
}

final voiceRecorderProvider = Provider<VoiceRecorder>((ref) {
  final recorder = PluginRecorder();
  ref.onDispose(recorder.dispose);
  return recorder;
});

final voiceSpeakerProvider = Provider<VoiceSpeaker>((ref) => PluginSpeaker());

/// Voice-activity detection thresholds (dBFS) and timings.
abstract final class Vad {
  static const speechLevel = -42.0;
  static const silenceLevel = -50.0;
  static const endOfSpeech = Duration(milliseconds: 1400);
  static const noSpeechTimeout = Duration(seconds: 8);
  static const maxUtterance = Duration(seconds: 45);
}

final _wake = RegExp(r'^\s*(?:hey|hi|ok(?:ay)?)[\s,]+dhanz\b[\s,.!?:]*', caseSensitive: false);

/// Returns the request with the wake phrase removed, or null if it does not start with "Hey Dhanz".
String? stripWakePhrase(String text) {
  final m = _wake.firstMatch(text);
  return m == null ? null : text.substring(m.end).trim();
}

/// Turns a Markdown answer into something pleasant to listen to.
String toSpeech(String markdown, {int maxChars = 1500}) {
  var t = markdown
      .replaceAll(RegExp(r'```[\s\S]*?```'), ' (I have put the code on screen.) ')
      .replaceAllMapped(RegExp(r'\[([^\]]+)\]\((?:[^)]+)\)'), (m) => m[1]!)
      .replaceAll(RegExp(r'\[\d+\]'), '')
      .replaceAllMapped(RegExp(r'`([^`]*)`'), (m) => m[1]!)
      .replaceAll(RegExp(r'^\s{0,3}#{1,6}\s*', multiLine: true), '')
      .replaceAll(RegExp(r'^\s*[-*+]\s+', multiLine: true), '')
      .replaceAll(RegExp(r'^\s*>\s?', multiLine: true), '')
      .replaceAll(RegExp(r'[*_~|]'), '')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();
  if (t.length > maxChars) {
    final cut = t.lastIndexOf('. ', maxChars);
    t = '${t.substring(0, cut > maxChars ~/ 2 ? cut + 1 : maxChars)} The full answer is on screen.';
  }
  return t;
}

class VoiceController extends Notifier<VoiceState> {
  StreamSubscription<double>? _levels;
  Timer? _maxTimer;
  DateTime? _speechStarted;
  DateTime? _silentSince;
  DateTime _listenStarted = DateTime.now();
  bool _finishing = false;
  int _session = 0;

  VoiceRecorder get _recorder => ref.read(voiceRecorderProvider);
  VoiceSpeaker get _speaker => ref.read(voiceSpeakerProvider);
  SecureStore get _store => ref.read(secureStoreProvider);

  @override
  VoiceState build() {
    ref.onDispose(_cleanup);
    unawaited(_loadSettings());
    return const VoiceState();
  }

  Future<void> _loadSettings() async {
    final voice = await _store.read('voice_name');
    final rate = double.tryParse(await _store.read('voice_rate') ?? '') ?? 0.5;
    List<String> voices = const [];
    try {
      voices = await _speaker.voices();
    } on Object {
      // TTS unavailable on this device
    }
    if (!ref.mounted) return;
    state = state.copyWith(voice: () => voice, rate: rate, voices: voices);
  }

  Future<void> setVoice(String? voice) async {
    state = state.copyWith(voice: () => voice);
    await _store.write('voice_name', voice);
  }

  Future<void> setRate(double rate) async {
    state = state.copyWith(rate: rate);
    await _store.write('voice_rate', rate.toStringAsFixed(2));
  }

  void setHandsFree(bool value) => state = state.copyWith(handsFree: value);

  void setWakePhrase(bool value) => state = state.copyWith(wakePhrase: value);

  /// Tap the mic: start listening, or finish the current utterance early.
  Future<void> toggle() async {
    switch (state.phase) {
      case VoicePhase.idle:
        await listen();
      case VoicePhase.listening:
        await _finishListening();
      case _:
        await stop();
    }
  }

  Future<void> listen() async {
    final session = ++_session;
    if (!await _recorder.hasPermission()) {
      state = state.copyWith(
        phase: VoicePhase.idle,
        error: () => 'Microphone access was denied. Allow it in your device settings to talk to Dhanz.',
      );
      return;
    }
    if (session != _session) return;
    _speechStarted = null;
    _silentSince = null;
    _finishing = false;
    _listenStarted = DateTime.now();
    await _recorder.start();
    state = state.copyWith(
      phase: VoicePhase.listening,
      error: () => null,
      status: () => state.wakePhrase ? 'Listening… say “Hey Dhanz” and your request' : 'Listening…',
    );
    await _levels?.cancel();
    _levels = _recorder.levels().listen(_onLevel);
    _maxTimer?.cancel();
    _maxTimer = Timer(Vad.maxUtterance, () => unawaited(_finishListening()));
  }

  void _onLevel(double db) {
    if (state.phase != VoicePhase.listening || _finishing) return;
    state = state.copyWith(level: db);
    final now = DateTime.now();
    if (db > Vad.speechLevel) {
      _speechStarted ??= now;
      _silentSince = null;
    } else if (_speechStarted != null && db < Vad.silenceLevel) {
      _silentSince ??= now;
      if (now.difference(_silentSince!) >= Vad.endOfSpeech) unawaited(_finishListening());
    } else if (_speechStarted == null && now.difference(_listenStarted) >= Vad.noSpeechTimeout) {
      unawaited(_noSpeech());
    }
  }

  Future<void> _noSpeech() async {
    if (_finishing) return;
    _finishing = true;
    _stopTimers();
    await _recorder.cancel();
    if (state.handsFree) {
      await listen(); // keep waiting quietly in hands-free mode
    } else {
      state = state.copyWith(phase: VoicePhase.idle, status: () => 'I didn’t hear anything.');
    }
  }

  Future<void> _finishListening() async {
    if (_finishing || state.phase != VoicePhase.listening) return;
    _finishing = true;
    final session = _session;
    _stopTimers();
    final recording = await _recorder.stop();
    if (session != _session) return;
    if (recording == null || recording.bytes.isEmpty) {
      state = state.copyWith(phase: VoicePhase.idle, status: () => 'Nothing was recorded.');
      return;
    }
    state = state.copyWith(phase: VoicePhase.transcribing, status: () => 'Understanding…', level: -160);
    String text;
    try {
      text = await ref.read(apiClientProvider).transcribe(recording.bytes, filename: recording.filename);
    } on ApiException catch (e) {
      state = state.copyWith(phase: VoicePhase.idle, error: () => e.message, status: () => null);
      return;
    }
    if (session != _session) return;
    await handleTranscript(text);
  }

  /// Acts on what the user said (public for tests).
  Future<void> handleTranscript(String text) async {
    final session = _session;
    var request = text.trim();
    if (request.isEmpty) {
      state = state.copyWith(transcript: () => null, status: () => 'Sorry, I didn’t catch that.');
      return state.handsFree ? listen() : _idle();
    }
    if (state.wakePhrase) {
      final stripped = stripWakePhrase(request);
      if (stripped == null) {
        state = state.copyWith(transcript: () => request, status: () => 'Waiting for “Hey Dhanz”…');
        return state.handsFree ? listen() : _idle();
      }
      request = stripped;
      if (request.isEmpty) {
        await _say('Yes?');
        return listen();
      }
    }
    state = state.copyWith(
      phase: VoicePhase.thinking,
      transcript: () => request,
      reply: () => null,
      status: () => 'Thinking…',
    );
    await ref.read(chatControllerProvider.notifier).send(request);
    if (session != _session) return;
    final chat = ref.read(chatControllerProvider);
    final last = chat.messages.isEmpty ? null : chat.messages.last;
    if (last == null || last.isUser || last.status != MessageStatus.complete) {
      state = state.copyWith(
        phase: VoicePhase.idle,
        error: () => last?.error ?? chat.error ?? 'Dhanz could not answer that.',
        status: () => null,
      );
      return;
    }
    state = state.copyWith(reply: () => last.content);
    await _say(toSpeech(last.content));
    if (session != _session) return;
    if (state.handsFree) {
      await listen();
    } else {
      _idle();
      state = state.copyWith(status: () => null);
    }
  }

  Future<void> _say(String text) async {
    state = state.copyWith(phase: VoicePhase.speaking, status: () => 'Speaking…');
    try {
      await _speaker.configure(voice: state.voice, rate: state.rate);
      await _speaker.speak(text);
    } on Object {
      state = state.copyWith(error: () => 'Text-to-speech is not available on this device.');
    }
  }

  /// Back to idle, keeping any status hint (e.g. "Waiting for “Hey Dhanz”") visible.
  void _idle() => state = state.copyWith(phase: VoicePhase.idle, level: -160);

  /// Stop everything: recording, generation and speech. Ends hands-free mode.
  Future<void> stop() async {
    _session++;
    _stopTimers();
    if (state.phase == VoicePhase.listening) await _recorder.cancel();
    if (state.phase == VoicePhase.thinking) ref.read(chatControllerProvider.notifier).stop();
    if (state.phase == VoicePhase.speaking) await _speaker.stop();
    state = state.copyWith(phase: VoicePhase.idle, handsFree: false, status: () => null, level: -160);
  }

  void _stopTimers() {
    _maxTimer?.cancel();
    _maxTimer = null;
    unawaited(_levels?.cancel());
    _levels = null;
  }

  void _cleanup() {
    _session++;
    _stopTimers();
  }
}

final voiceControllerProvider = NotifierProvider<VoiceController, VoiceState>(VoiceController.new);
