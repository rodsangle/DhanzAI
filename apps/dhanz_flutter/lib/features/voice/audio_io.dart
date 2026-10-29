import 'dart:async';

import 'package:cross_file/cross_file.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:path_provider/path_provider.dart';
import 'package:record/record.dart';

import 'delete_file_stub.dart' if (dart.library.io) 'delete_file_io.dart';

/// A finished recording, ready to upload for transcription.
typedef Recording = ({Uint8List bytes, String filename});

/// Microphone access (replaced by fakes in tests).
abstract class VoiceRecorder {
  Future<bool> hasPermission();
  Future<void> start();

  /// Input level in dBFS (about -160 = silence, 0 = loudest), sampled while recording.
  Stream<double> levels();
  Future<Recording?> stop();
  Future<void> cancel();
  Future<void> dispose();
}

/// Text-to-speech output (replaced by fakes in tests).
abstract class VoiceSpeaker {
  Future<List<String>> voices();
  Future<void> configure({String? voice, double rate});

  /// Speaks [text] and completes when speech has finished (or was stopped).
  Future<void> speak(String text);
  Future<void> stop();
}

/// Records AAC (.m4a) with the `record` plugin: Android, iOS, macOS and Windows.
class PluginRecorder implements VoiceRecorder {
  final _recorder = AudioRecorder();

  @override
  Future<bool> hasPermission() => _recorder.hasPermission();

  @override
  Future<void> start() async {
    // On the web the plugin records to a blob URL and ignores the path.
    final path = kIsWeb
        ? ''
        : '${(await getTemporaryDirectory()).path}/dhanz_${DateTime.now().millisecondsSinceEpoch}.m4a';
    await _recorder.start(
      const RecordConfig(encoder: AudioEncoder.aacLc, sampleRate: 16000, numChannels: 1, bitRate: 64000),
      path: path,
    );
  }

  @override
  Stream<double> levels() => _recorder.onAmplitudeChanged(const Duration(milliseconds: 150)).map((a) => a.current);

  @override
  Future<Recording?> stop() async {
    final path = await _recorder.stop();
    if (path == null) return null;
    final bytes = await XFile(path).readAsBytes();
    if (!kIsWeb) {
      try {
        await deleteTempFile(path); // never keep recordings on the device
      } on Object {
        // best effort
      }
    }
    return (bytes: bytes, filename: 'speech.m4a');
  }

  @override
  Future<void> cancel() => _recorder.cancel();

  @override
  Future<void> dispose() => _recorder.dispose();
}

/// Device text-to-speech via `flutter_tts` (SAPI on Windows, AVSpeech on iOS/macOS, Android TTS).
class PluginSpeaker implements VoiceSpeaker {
  PluginSpeaker() {
    unawaited(_tts.awaitSpeakCompletion(true));
  }

  final _tts = FlutterTts();

  @override
  Future<List<String>> voices() async {
    final raw = await _tts.getVoices;
    if (raw is! List) return const [];
    return [
      for (final v in raw)
        if (v is Map && v['name'] != null) '${v['name']}|${v['locale'] ?? ''}',
    ];
  }

  @override
  Future<void> configure({String? voice, double rate = 0.5}) async {
    await _tts.setSpeechRate(rate);
    if (voice != null && voice.contains('|')) {
      final [name, locale] = voice.split('|');
      await _tts.setVoice({'name': name, 'locale': locale});
    }
  }

  @override
  Future<void> speak(String text) async {
    await _tts.speak(text);
  }

  @override
  Future<void> stop() async {
    await _tts.stop();
  }
}
