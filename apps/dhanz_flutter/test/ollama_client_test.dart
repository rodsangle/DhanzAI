import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:dhanz_ai/core/api/ollama_client.dart';

void main() {
  test('connection test uses loopback and checks selected model', () async {
    final client = OllamaClient(
      clientFactory: () => MockClient((request) async {
        expect(request.url.toString(), 'http://127.0.0.1:11434/v1/models');
        expect(request.headers.containsKey('authorization'), isFalse);
        return http.Response('{"data":[{"id":"qwen3:8b"}]}', 200);
      }),
    );
    await client.testConnection('qwen3:8b');
    await expectLater(client.testConnection('qwen3:14b'), throwsA(isA<LocalAiException>()));
  });

  test('OpenAI stream handles split UTF8 bytes, comments, empty choices and DONE', () async {
    final bytes = utf8.encode(
      ': ping\r\ndata: {"choices":[]}\r\n\r\n'
      'data: {"choices":[{"delta":{"content":"你好"}}]}\n\n'
      'data: [DONE]\n\n',
    );
    final client = OllamaClient(
      clientFactory: () => MockClient.streaming((request, body) async {
        expect(request.url.path, '/v1/chat/completions');
        final payload = jsonDecode(await body.bytesToString());
        expect(payload['model'], 'qwen3:14b');
        expect(payload['stream'], isTrue);
        expect(payload['messages'][0]['content'], 'hello');
        expect(request.headers.containsKey('authorization'), isFalse);
        return http.StreamedResponse(Stream.fromIterable(bytes.map((b) => [b])), 200);
      }),
    );
    expect(
      await client.stream([
        {'role': 'user', 'content': 'hello'},
      ], 'qwen3:14b').toList(),
      ['你好'],
    );
  });

  test('missing model and interrupted stream are actionable failures', () async {
    final missing = OllamaClient(clientFactory: () => MockClient((_) async => http.Response('', 404)));
    await expectLater(missing.stream([], 'qwen3:8b').toList(), throwsA(isA<LocalAiException>()));
    final truncated = OllamaClient(
      clientFactory: () =>
          MockClient((_) async => http.Response('data: {"choices":[{"delta":{"content":"partial"}}]}\n\n', 200)),
    );
    await expectLater(truncated.stream([], 'qwen3:8b').toList(), throwsA(isA<LocalAiException>()));
  });

  for (final route in AiRoute.values) {
    test('$route routing and fallback', () async {
      var cloudCalls = 0;
      final labels = <String>[];
      final result = routeReply(
        route: route,
        local: () => Stream.error(const LocalAiException('offline')),
        cloud: () {
          cloudCalls++;
          return Stream.value('cloud reply');
        },
        onRoute: labels.add,
      ).toList();
      if (route == AiRoute.local) {
        await expectLater(result, throwsA(isA<LocalAiException>()));
        expect(cloudCalls, 0);
      } else {
        expect(await result, ['cloud reply']);
        expect(cloudCalls, 1);
      }
    });
  }

  test('Hybrid success never invokes cloud', () async {
    expect(
      await routeReply(
        route: AiRoute.hybrid,
        local: () => Stream.value('local'),
        cloud: () => throw StateError('must not call cloud'),
        onRoute: (_) {},
      ).toList(),
      ['local'],
    );
  });

  test('Hybrid never falls back after partial output', () async {
    Stream<String> partial() async* {
      yield 'partial';
      throw const LocalAiException('disconnected');
    }

    await expectLater(
      routeReply(
        route: AiRoute.hybrid,
        local: partial,
        cloud: () => throw StateError('must not send to cloud'),
        onRoute: (_) {},
      ).toList(),
      throwsA(isA<LocalAiException>()),
    );
  });
}
