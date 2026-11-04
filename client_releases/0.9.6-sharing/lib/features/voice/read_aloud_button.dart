import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import 'voice_controller.dart';

/// One reader across chat and Studio, with explicit start/stop and no autoplay.
final readAloudProvider = NotifierProvider<ReadAloudController, String?>(ReadAloudController.new);

class ReadAloudController extends Notifier<String?> {
  int _session = 0;

  @override
  String? build() => null;

  Future<void> stop([String? owner]) async {
    if (!ref.mounted) return;
    if (owner != null && state != owner) return;
    _session++;
    state = null;
    await ref.read(voiceSpeakerProvider).stop();
  }

  Future<void> read(String owner, String text) async {
    await stop();
    final session = ++_session;
    state = owner;
    final speaker = ref.read(voiceSpeakerProvider);
    try {
      final store = ref.read(secureStoreProvider);
      final voice = await store.read('voice_name');
      final rate = double.tryParse(await store.read('voice_rate') ?? '') ?? 0.5;
      if (session != _session) return;
      await speaker.configure(voice: voice, rate: rate);
      final spoken = toSpeech(text, maxChars: 100000);
      // Android engines commonly limit each utterance to 4,000 characters.
      for (var offset = 0; offset < spoken.length;) {
        if (session != _session) return;
        var end = (offset + 1800).clamp(0, spoken.length);
        if (end < spoken.length) {
          final boundary = spoken.lastIndexOf(' ', end);
          if (boundary > offset) end = boundary;
        }
        await speaker.speak(spoken.substring(offset, end));
        offset = end;
      }
    } finally {
      if (ref.mounted && session == _session) state = null;
    }
  }
}

class ReadAloudButton extends ConsumerStatefulWidget {
  const ReadAloudButton({super.key, required this.text, this.label = 'Read aloud'});
  final String text;
  final String label;

  @override
  ConsumerState<ReadAloudButton> createState() => _ReadAloudButtonState();
}

class _ReadAloudButtonState extends ConsumerState<ReadAloudButton> with WidgetsBindingObserver {
  late final String _owner = 'reader-${identityHashCode(this)}';
  late ReadAloudController _reader;

  @override
  void initState() {
    super.initState();
    _reader = ref.read(readAloudProvider.notifier);
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.hidden || state == AppLifecycleState.paused) {
      unawaited(_reader.stop(_owner));
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!TickerMode.valuesOf(context).enabled) {
      scheduleMicrotask(() => unawaited(_reader.stop(_owner)));
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    // Do not update a provider while Flutter is tearing down the widget tree.
    scheduleMicrotask(() => unawaited(_reader.stop(_owner)));
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final speaking = ref.watch(readAloudProvider) == _owner;
    return IconButton(
      tooltip: speaking ? 'Stop reading' : widget.label,
      icon: Icon(speaking ? Icons.stop_circle_outlined : Icons.volume_up_outlined),
      onPressed: widget.text.trim().isEmpty
          ? null
          : () async {
              try {
                if (speaking) {
                  await _reader.stop(_owner);
                } else {
                  await _reader.read(_owner, widget.text);
                }
              } on Object {
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Speech playback is unavailable. Check your device voice settings.')),
                  );
                }
              }
            },
    );
  }
}
