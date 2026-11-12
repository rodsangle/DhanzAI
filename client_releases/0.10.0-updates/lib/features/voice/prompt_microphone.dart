import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import 'audio_io.dart';
import 'voice_controller.dart' show Vad;

/// Dictates into a prompt. It never submits a generation or sends a chat.
class PromptMicrophone extends ConsumerStatefulWidget {
  const PromptMicrophone({
    super.key,
    required this.onTranscript,
    required this.onError,
    this.enabled = true,
    this.recorderFactory,
    this.compact = false,
    this.label = 'Dictate prompt',
  });
  final ValueChanged<String> onTranscript;
  final ValueChanged<String> onError;
  final bool enabled;
  final VoiceRecorder Function()? recorderFactory;
  final bool compact;
  final String label;

  @override
  ConsumerState<PromptMicrophone> createState() => _PromptMicrophoneState();
}

class _PromptMicrophoneState extends ConsumerState<PromptMicrophone> with WidgetsBindingObserver {
  static _PromptMicrophoneState? _active;
  VoiceRecorder? _recorder;
  StreamSubscription<double>? _levels;
  Timer? _deadline;
  bool _listening = false, _transcribing = false, _starting = false;
  int _session = 0;
  DateTime? _silentSince;
  bool _heardSpeech = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused || state == AppLifecycleState.hidden || state == AppLifecycleState.detached) {
      unawaited(_cancel());
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!TickerMode.valuesOf(context).enabled && (_listening || _transcribing)) unawaited(_cancel());
  }

  void _timers() {
    _deadline?.cancel();
    _deadline = null;
    unawaited(_levels?.cancel());
    _levels = null;
  }

  Future<void> _cancel() async {
    _session++;
    _timers();
    if (_listening) {
      try {
        await _recorder?.cancel();
      } on Object {
        /* Device was removed. */
      }
    }
    if (identical(_active, this)) _active = null;
    if (mounted) {
      setState(() {
        _listening = false;
        _transcribing = false;
        _starting = false;
      });
    }
  }

  Future<void> _start() async {
    await _active?._cancel();
    if (!mounted) return;
    final session = ++_session;
    _active = this;
    setState(() => _starting = true);
    final recorder = _recorder ??= widget.recorderFactory?.call() ?? PluginRecorder();
    try {
      if (!await recorder.hasPermission()) throw const _MicrophoneDenied();
      if (!mounted || session != _session) return;
      await recorder.start();
      if (!mounted || session != _session) {
        await recorder.cancel();
        return;
      }
      _silentSince = null;
      _heardSpeech = false;
      setState(() {
        _starting = false;
        _listening = true;
      });
      _levels = recorder.levels().listen(
        (db) {
          if (!_listening) return;
          final now = DateTime.now();
          if (db > Vad.speechLevel) {
            _heardSpeech = true;
            _silentSince = null;
          } else if (_heardSpeech && db < Vad.silenceLevel) {
            _silentSince ??= now;
            if (now.difference(_silentSince!) >= Vad.endOfSpeech) unawaited(_finish());
          }
        },
        onError: (Object _) {
          /* The stop button and deadline remain usable without a level meter. */
        },
      );
      _deadline = Timer(Vad.maxUtterance, () => unawaited(_finish()));
    } on Object catch (error) {
      if (!mounted || session != _session) return;
      await _cancel();
      if (mounted) {
        widget.onError(
          error is _MicrophoneDenied
              ? 'Microphone access was denied. Allow DHANZ AI microphone access in device settings.'
              : 'Could not start the microphone. Check your input device and try again.',
        );
      }
    }
  }

  Future<void> _finish() async {
    if (!_listening) return;
    final session = _session;
    _timers();
    setState(() {
      _listening = false;
      _transcribing = true;
    });
    try {
      final audio = await _recorder!.stop();
      if (audio == null || audio.bytes.isEmpty) throw const _EmptyRecording();
      if (!mounted || session != _session) return;
      final text = await ref.read(apiClientProvider).transcribe(audio.bytes, filename: audio.filename);
      if (!mounted || session != _session) return;
      if (text.trim().isEmpty) throw const _EmptyRecording();
      widget.onTranscript(text.trim());
    } on Object catch (error) {
      if (mounted && session == _session) {
        widget.onError(
          error is ApiException
              ? error.message
              : error is _EmptyRecording
              ? 'No speech was recognized. Try again closer to the microphone.'
              : 'Speech recognition failed. Please try recording again.',
        );
      }
    } finally {
      if (mounted && session == _session) setState(() => _transcribing = false);
      if (identical(_active, this) && session == _session) _active = null;
    }
  }

  @override
  void dispose() {
    _session++;
    _timers();
    WidgetsBinding.instance.removeObserver(this);
    if (identical(_active, this)) _active = null;
    final recorder = _recorder;
    if (recorder != null) {
      unawaited(() async {
        try {
          await recorder.cancel();
        } on Object {
          /* Best effort. */
        }
        try {
          await recorder.dispose();
        } on Object {
          /* Best effort. */
        }
      }());
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final onPressed = !widget.enabled
        ? null
        : () => _listening
              ? _finish()
              : (_transcribing || _starting)
              ? _cancel()
              : _start();
    final icon = Icon(
      _listening
          ? Icons.stop_circle
          : _transcribing
          ? Icons.close
          : Icons.mic,
    );
    final label = _listening
        ? 'Stop recording'
        : _transcribing
        ? 'Cancel transcription'
        : _starting
        ? 'Cancel microphone'
        : widget.label;
    return widget.compact
        ? IconButton(onPressed: onPressed, icon: icon, tooltip: label)
        : OutlinedButton.icon(onPressed: onPressed, icon: icon, label: Text(label));
  }
}

class _MicrophoneDenied {
  const _MicrophoneDenied();
}

class _EmptyRecording {
  const _EmptyRecording();
}
