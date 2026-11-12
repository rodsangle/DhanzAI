import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

enum AiRoute { local, cloud, hybrid }

const localModels = ['qwen3:8b', 'qwen3:14b'];

class LocalAiException implements Exception {
  const LocalAiException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Dedicated unauthenticated transport. No backend tokens ever reach Ollama.
class OllamaClient {
  OllamaClient({http.Client Function()? clientFactory}) : _factory = clientFactory ?? http.Client.new;

  static final baseUri = Uri.parse('http://127.0.0.1:11434/v1/');
  final http.Client Function() _factory;
  http.Client? _active;

  Future<void> testConnection(String model) async {
    final client = _factory();
    try {
      final response = await client.get(baseUri.resolve('models')).timeout(const Duration(seconds: 5));
      if (response.statusCode != 200) throw const LocalAiException('Ollama connection test failed.');
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final models = (body['data'] as List).map((m) => m['id']);
      if (!models.contains(model)) throw LocalAiException('Model missing. Run: ollama pull $model');
    } on TimeoutException {
      throw const LocalAiException('Ollama timed out. Start Ollama and try again.');
    } on http.ClientException {
      throw const LocalAiException('Ollama is offline. Start Ollama on this PC.');
    } finally {
      client.close();
    }
  }

  Stream<String> stream(List<Map<String, String>> messages, String model) async* {
    if (!localModels.contains(model)) throw const LocalAiException('Unsupported local model.');
    final client = _factory();
    _active = client;
    try {
      final request = http.Request('POST', baseUri.resolve('chat/completions'))
        ..headers.addAll({'Content-Type': 'application/json', 'Accept': 'text/event-stream'})
        ..body = jsonEncode({'model': model, 'messages': messages, 'stream': true});
      // A cold model can take minutes to load before Ollama returns headers.
      final response = await client.send(request).timeout(const Duration(minutes: 3));
      if (response.statusCode != 200) {
        throw LocalAiException(
          response.statusCode == 404
              ? 'Model missing. Run: ollama pull $model'
              : 'Ollama request failed (${response.statusCode}).',
        );
      }
      final lines = const LineSplitter().bind(utf8.decoder.bind(response.stream)).timeout(const Duration(minutes: 3));
      var emitted = false;
      await for (final line in lines) {
        if (!line.startsWith('data:')) continue;
        final raw = line.substring(5).trim();
        if (raw == '[DONE]') {
          if (!emitted) throw const LocalAiException('Ollama returned an empty reply. Try again.');
          return;
        }
        if (raw.isEmpty) continue;
        final data = jsonDecode(raw) as Map<String, dynamic>;
        if (data['error'] != null) throw const LocalAiException('Ollama could not generate a reply.');
        final choices = data['choices'] as List?;
        if (choices == null || choices.isEmpty) continue;
        final delta = choices.first['delta'] as Map?;
        final content = delta?['content'] as String?;
        if (content != null && content.isNotEmpty) {
          emitted = true;
          yield content;
        }
      }
      throw const LocalAiException('Ollama connection ended before the reply completed.');
    } on TimeoutException {
      throw const LocalAiException('Ollama timed out. Try the 8B model or restart Ollama.');
    } on http.ClientException {
      throw const LocalAiException('Ollama is offline. Start Ollama on this PC and retry.');
    } finally {
      client.close();
      if (identical(_active, client)) _active = null;
    }
  }

  void cancel() {
    _active?.close();
    _active = null;
  }
}

/// Hybrid may send history to the existing backend, but never after partial output.
Stream<String> routeReply({
  required AiRoute route,
  required Stream<String> Function() local,
  required Stream<String> Function() cloud,
  required void Function(String) onRoute,
}) async* {
  if (route == AiRoute.cloud) {
    onRoute('Cloud');
    yield* cloud();
    return;
  }
  var emitted = false;
  try {
    onRoute('Local');
    await for (final text in local()) {
      emitted = true;
      yield text;
    }
  } on Exception {
    if (route != AiRoute.hybrid || emitted) rethrow;
    onRoute('Cloud fallback');
    yield* cloud();
  }
}
