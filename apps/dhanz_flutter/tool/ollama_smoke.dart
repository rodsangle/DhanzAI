import 'dart:io';

import 'package:dhanz_ai/core/api/ollama_client.dart';

/// Opt-in integration check: run with `dart run tool/ollama_smoke.dart`.
Future<void> main() async {
  for (final model in localModels) {
    final client = OllamaClient();
    try {
      await client.testConnection(model);
      final first = await client
          .stream([
            {'role': 'user', 'content': '/no_think Reply with the word READY.'},
          ], model)
          .first
          .timeout(const Duration(minutes: 3));
      if (first.isEmpty) throw StateError('Empty streaming response');
      stdout.writeln('$model: connection and streamed content OK');
    } finally {
      client.cancel();
    }
  }
}
