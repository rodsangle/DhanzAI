import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// Speech is provided by the browser or operating system, not a Dhanz AI API.
abstract class ReplySpeech {
  Future<void> speak(String text);
  Future<void> stop();
}

class DeviceReplySpeech implements ReplySpeech {
  final FlutterTts _tts = FlutterTts();
  Future<void>? _ready;

  Future<void> _initialize() async {
    await _tts.awaitSpeakCompletion(true);
    await _tts.setSpeechRate(0.5);
  }

  @override
  Future<void> speak(String text) async {
    try {
      await (_ready ??= _initialize());
    } on Object {
      _ready = null;
      rethrow;
    }
    final result = await _tts.speak(text);
    if (result == 0) throw StateError('Speech is unavailable');
  }

  @override
  Future<void> stop() async {
    await _tts.stop();
  }
}

/// Keep all prose, but avoid reading Markdown syntax, URLs and fenced code aloud.
String replySpeechText(String markdown) => markdown
    .replaceAll(RegExp(r'```[\s\S]*?```'), ' Code is available on screen. ')
    .replaceAll(RegExp(r'!\[[^\]]*\]\([^)]*\)'), '')
    .replaceAllMapped(RegExp(r'\[([^\]]+)\]\([^)]*\)'), (match) => match[1]!)
    .replaceAllMapped(RegExp(r'`([^`]*)`'), (match) => match[1]!)
    .replaceAll(RegExp(r'^\s{0,3}#{1,6}\s+', multiLine: true), '')
    .replaceAll(RegExp(r'^\s*(?:[-*+]|\d+[.)])\s+', multiLine: true), '')
    .replaceAll(RegExp(r'^\s*>\s?', multiLine: true), '')
    .replaceAll(RegExp(r'[*_~|]'), '')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();

/// Chunk long replies for engines with utterance limits; never truncate the reply.
List<String> replySpeechChunks(String text, {int limit = 1000}) {
  if (limit < 2) throw ArgumentError.value(limit, 'limit');
  final chunks = <String>[];
  var remaining = text.trim();
  while (remaining.length > limit) {
    var cut = remaining.lastIndexOf(' ', limit);
    if (cut < limit ~/ 2) cut = limit;
    // Do not split a UTF-16 surrogate pair.
    final preceding = remaining.codeUnitAt(cut - 1);
    if (preceding >= 0xD800 && preceding <= 0xDBFF) cut--;
    chunks.add(remaining.substring(0, cut));
    remaining = remaining.substring(cut).trimLeft();
  }
  if (remaining.isNotEmpty) chunks.add(remaining);
  return chunks;
}

/// One active reply across the chat. Generation checks ignore stale completions.
class ReplyReader extends ChangeNotifier {
  ReplyReader(this.speech);

  final ReplySpeech speech;
  Object? _owner;
  int _generation = 0;

  bool isReading(Object owner) => identical(_owner, owner);

  Future<void> toggle(Object owner, String markdown) async {
    if (isReading(owner)) {
      await stop(owner);
      return;
    }
    final text = replySpeechText(markdown);
    if (text.isEmpty) throw StateError('There is no readable text in this reply.');
    final generation = ++_generation;
    _owner = owner;
    notifyListeners();
    try {
      await speech.stop();
      if (generation != _generation) return;
      for (final chunk in replySpeechChunks(text)) {
        if (generation != _generation) return;
        await speech.speak(chunk);
      }
    } on Object {
      if (generation == _generation) rethrow;
    } finally {
      if (generation == _generation) {
        _owner = null;
        notifyListeners();
      }
    }
  }

  Future<void> stop(Object owner) async {
    if (!isReading(owner)) return;
    ++_generation;
    _owner = null;
    notifyListeners();
    await speech.stop();
  }
}

final _deviceReplyReader = ReplyReader(DeviceReplySpeech());

class ReadAloudButton extends StatefulWidget {
  const ReadAloudButton({super.key, required this.text, this.reader});

  final String text;
  final ReplyReader? reader;

  @override
  State<ReadAloudButton> createState() => _ReadAloudButtonState();
}

class _ReadAloudButtonState extends State<ReadAloudButton> with WidgetsBindingObserver {
  final Object _owner = Object();
  ReplyReader get _reader => widget.reader ?? _deviceReplyReader;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _reader.addListener(_changed);
  }

  void _changed() {
    if (!mounted) return;
    if (SchedulerBinding.instance.schedulerPhase == SchedulerPhase.persistentCallbacks) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() {});
      });
    } else {
      setState(() {});
    }
  }

  Future<void> _stop() async {
    try {
      await _reader.stop(_owner);
    } on Object {
      // Best effort when a browser tab closes or the engine disappears.
    }
  }

  @override
  void didUpdateWidget(covariant ReadAloudButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    final oldReader = oldWidget.reader ?? _deviceReplyReader;
    if (oldReader != _reader) {
      oldReader.removeListener(_changed);
      unawaited(oldReader.stop(_owner).catchError((Object _) {}));
      _reader.addListener(_changed);
    } else if (oldWidget.text != widget.text) {
      unawaited(_stop());
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) unawaited(_stop());
  }

  @override
  void deactivate() {
    unawaited(_stop());
    super.deactivate();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _reader.removeListener(_changed);
    unawaited(_stop());
    super.dispose();
  }

  Future<void> _toggle() async {
    try {
      await _reader.toggle(_owner, widget.text);
    } on Object {
      if (!mounted) return;
      ScaffoldMessenger.maybeOf(context)?.showSnackBar(
        const SnackBar(
          content: Text('Read aloud is unavailable. Check your device’s speech voices or try another browser.'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final reading = _reader.isReading(_owner);
    return IconButton(
      tooltip: reading ? 'Stop reading' : 'Read aloud',
      icon: Icon(reading ? Icons.stop_circle_outlined : Icons.volume_up_outlined),
      iconSize: 18,
      visualDensity: VisualDensity.compact,
      color: Theme.of(context).colorScheme.onSurfaceVariant,
      onPressed: () => unawaited(_toggle()),
    );
  }
}
