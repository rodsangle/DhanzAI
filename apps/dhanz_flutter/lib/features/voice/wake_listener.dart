import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'voice_controller.dart';
import 'wake_recognizer.dart';

final wakeRecognizerProvider = Provider<WakeRecognizer>((ref) => createWakeRecognizer());

/// Explicit foreground-only opt-in. Recognition is paused while Dhanz answers.
class WakeListener extends ConsumerStatefulWidget {
  const WakeListener({super.key, this.onEnabled});
  final ValueChanged<bool>? onEnabled;
  @override
  ConsumerState<WakeListener> createState() => _WakeListenerState();
}

class _WakeListenerState extends ConsumerState<WakeListener> with WidgetsBindingObserver {
  late final WakeRecognizer _recognizer;
  bool _enabled = false, _processing = false;
  String _status = 'Off';
  Timer? _restart;
  DateTime? _awakened;
  DateTime _startedAt = DateTime.now();
  int _session = 0;
  int _emptyEnds = 0;
  @override
  void initState() {
    super.initState();
    _recognizer = ref.read(wakeRecognizerProvider);
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) {
      _disable('Paused when the app left the foreground. Turn on again to listen.');
    }
  }

  void _disable(String status) {
    _session++;
    _awakened = null;
    _restart?.cancel();
    _recognizer.stop();
    if (mounted) {
      setState(() {
        _enabled = false;
        _status = status;
      });
      widget.onEnabled?.call(false);
    }
  }

  void _start() {
    if (!_enabled || _processing || !mounted) return;
    final session = ++_session;
    _startedAt = DateTime.now();
    try {
      _recognizer.start(
        onText: (text) {
          if (!_enabled || _processing || session != _session) return;
          _emptyEnds = 0;
          final stripped = stripWakePhrase(text);
          if (stripped != null && stripped.isEmpty) {
            _awakened = DateTime.now();
            setState(() => _status = 'Yes? Say your request within 10 seconds.');
            return;
          }
          final waiting = _awakened != null && DateTime.now().difference(_awakened!) < const Duration(seconds: 10);
          final request = stripped ?? (waiting ? text.trim() : '');
          if (request.isEmpty) return;
          _awakened = null;
          unawaited(_answer(request, session));
        },
        onError: (error) {
          if (error == 'no-speech') return; // Normal browser silence; onEnd rearms recognition.
          if (session == _session) _disable('Wake listening stopped: $error. Check browser microphone permission.');
        },
        onEnd: () {
          if (!_enabled || _processing || session != _session) return;
          _emptyEnds = DateTime.now().difference(_startedAt) < const Duration(seconds: 2) ? _emptyEnds + 1 : 0;
          if (_emptyEnds >= 3) {
            _disable('The browser ended listening repeatedly. Turn on to try again.');
            return;
          }
          _restart?.cancel();
          _restart = Timer(const Duration(seconds: 1), _start);
        },
      );
      setState(() => _status = 'Listening for “Hey Dhanz”…');
    } on Object {
      _disable('Could not start browser speech recognition. Use the microphone button.');
    }
  }

  Future<void> _answer(String request, int session) async {
    _processing = true;
    _restart?.cancel();
    _recognizer.stop();
    setState(() => _status = 'Answering… wake microphone paused');
    final voice = ref.read(voiceControllerProvider.notifier);
    voice.setHandsFree(false);
    voice.setWakePhrase(false);
    try {
      await voice.handleTranscript(request);
    } on Object {
      if (mounted && session == _session) _disable('Voice request failed. Turn on to try again.');
    } finally {
      _processing = false;
      if (mounted && _enabled && session == _session) _start();
    }
  }

  Future<void> _toggle(bool value) async {
    if (!value) {
      _disable('Off');
      await ref.read(voiceControllerProvider.notifier).stop();
      return;
    }
    final accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Enable “Hey Dhanz”?'),
        content: const Text(
          'The microphone listens while this Voice screen is open. Your browser may send speech to its recognition service. Only requests after “Hey Dhanz” are sent to Dhanz. Listening stops when you leave or hide the app. Device lock/background listening is not supported.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Enable microphone')),
        ],
      ),
    );
    if (accepted != true || !mounted) return;
    await ref.read(voiceControllerProvider.notifier).stop();
    if (!mounted) return;
    setState(() {
      _enabled = true;
      _emptyEnds = 0;
    });
    widget.onEnabled?.call(true);
    _start();
  }

  @override
  void dispose() {
    _session++;
    _restart?.cancel();
    _recognizer.stop();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SwitchListTile(
    title: const Text('Listen for “Hey Dhanz”'),
    subtitle: Text(_recognizer.supported ? _status : 'Unavailable in this browser. Use the microphone button.'),
    value: _enabled,
    onChanged: _recognizer.supported && (_enabled || !_processing) ? _toggle : null,
  );
}
