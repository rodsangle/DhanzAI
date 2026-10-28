import 'dart:async';
import 'dart:convert';

import '../../models/models.dart';

/// Decodes a `text/event-stream` byte stream into [ChatEvent]s.
Stream<ChatEvent> decodeSse(Stream<List<int>> bytes) async* {
  String? event;
  final data = <String>[];
  await for (final line in const LineSplitter().bind(utf8.decoder.bind(bytes))) {
    if (line.isEmpty) {
      if (data.isNotEmpty) {
        yield _toEvent(event, data.join('\n'));
      }
      event = null;
      data.clear();
      continue;
    }
    if (line.startsWith(':')) continue;
    final idx = line.indexOf(':');
    final field = idx == -1 ? line : line.substring(0, idx);
    var value = idx == -1 ? '' : line.substring(idx + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    if (field == 'event') {
      event = value;
    } else if (field == 'data') {
      data.add(value);
    }
  }
  if (data.isNotEmpty) yield _toEvent(event, data.join('\n'));
}

ChatEvent _toEvent(String? event, String raw) {
  final decoded = jsonDecode(raw) as Map<String, dynamic>;
  return ChatEvent(event ?? decoded['type'] as String? ?? 'message', decoded);
}
