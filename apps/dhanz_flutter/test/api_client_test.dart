import 'dart:convert';

import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/api/sse.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;
  late ApiClient api;

  setUp(() {
    backend = FakeBackend();
    store = MemorySecureStore();
    api = ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client);
  });

  test('decodeSse handles multi-line data, comments and split chunks', () async {
    final raw =
        ': keepalive\n\nevent: delta\ndata: {"type":"delta",\ndata: "text":"hi"}\n\nevent: done\ndata: {"type":"done"}\n';
    final bytes = Stream.fromIterable([utf8.encode(raw.substring(0, 17)), utf8.encode(raw.substring(17))]);
    final events = await decodeSse(bytes).toList();
    expect(events.map((e) => e.type), ['delta', 'done']);
    expect(events.first.data['text'], 'hi');
  });

  test('register stores tokens and returns the user', () async {
    final tokens = await api.register('Ada@Example.com', 'pw-1234567890', 'Ada');
    expect(tokens.user.email, 'ada@example.com');
    expect(await store.read(StoreKeys.accessToken), backend.validAccess);
    expect(await api.hasSession(), isTrue);
  });

  test('expired access token is refreshed once and the request retried', () async {
    await api.register('a@b.co', 'pw-1234567890', 'A');
    await store.write(StoreKeys.accessToken, 'stale');
    final me = await api.me();
    expect(me.displayName, 'A');
    expect(backend.requests.where((r) => r == 'POST /auth/refresh'), hasLength(1));
  });

  test('failed refresh clears the session and notifies', () async {
    await api.register('a@b.co', 'pw-1234567890', 'A');
    await store.write(StoreKeys.accessToken, 'stale');
    await store.write(StoreKeys.refreshToken, 'revoked');
    var expired = false;
    api.onSessionExpired = () => expired = true;
    await expectLater(api.me(), throwsA(isA<ApiException>().having((e) => e.statusCode, 'status', 401)));
    expect(expired, isTrue);
    expect(await api.hasSession(), isFalse);
  });

  test('API errors surface the server detail', () async {
    await expectLater(
      api.login('nobody@example.com', 'x'),
      throwsA(isA<ApiException>().having((e) => e.message, 'message', 'Invalid email or password')),
    );
  });

  test('streamChat yields protocol events', () async {
    await api.register('a@b.co', 'pw-1234567890', 'A');
    final conv = await api.createConversation();
    final stream = await api.streamChat(conv.id, content: 'hi', modelKey: 'echo:echo-1');
    final events = await stream.events.toList();
    expect(events.first.type, 'meta');
    expect(events.last.type, 'done');
    final text = events.where((e) => e.type == 'delta').map((e) => e.data['text']).join();
    expect(text, backend.reply);
  });
}
