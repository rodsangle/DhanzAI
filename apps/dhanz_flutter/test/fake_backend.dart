import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Minimal in-memory implementation of the DHANZ AI API used by tests.
class FakeBackend {
  final users = <String, Map<String, dynamic>>{};
  final conversations = <String, Map<String, dynamic>>{};
  final requests = <String>[];
  int _ids = 0;
  int _tokens = 0;
  String? validAccess;
  String? validRefresh;
  String reply = 'Hello from **Dhanz**.';

  String _id() => 'id-${_ids++}';

  Map<String, dynamic> get _user => users.values.first;

  Map<String, dynamic> _tokensFor(Map<String, dynamic> user) {
    validAccess = 'access-${_tokens++}';
    validRefresh = 'refresh-${_tokens++}';
    return {
      'access_token': validAccess,
      'refresh_token': validRefresh,
      'token_type': 'bearer',
      'expires_in': 900,
      'user': user,
    };
  }

  http.Client client() => MockClient.streaming(_handle);

  Future<http.StreamedResponse> _handle(http.BaseRequest req, http.ByteStream bodyStream) async {
    final bodyText = await bodyStream.bytesToString();
    final body = bodyText.isEmpty ? <String, dynamic>{} : jsonDecode(bodyText) as Map<String, dynamic>;
    final path = req.url.path.replaceFirst('/api/v1', '');
    requests.add('${req.method} $path');

    http.StreamedResponse json(Object? data, [int status = 200]) => http.StreamedResponse(
      Stream.value(utf8.encode(data == null ? '' : jsonEncode(data))),
      status,
      headers: {'content-type': 'application/json'},
    );

    if (path == '/auth/register') {
      final user = {
        'id': _id(),
        'email': (body['email'] as String).toLowerCase(),
        'display_name': body['display_name'],
        'role': 'user',
        'routing_policy': 'balanced',
        'preferred_model': null,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      };
      users[user['email'] as String] = user;
      return json(_tokensFor(user), 201);
    }
    if (path == '/auth/login') {
      final user = users[(body['email'] as String).toLowerCase()];
      if (user == null) return json({'detail': 'Invalid email or password'}, 401);
      return json(_tokensFor(user));
    }
    if (path == '/auth/refresh') {
      if (body['refresh_token'] != validRefresh) return json({'detail': 'Session expired'}, 401);
      return json(_tokensFor(_user));
    }
    if (path == '/auth/logout') return json(null, 204);

    if (req.headers['Authorization'] != 'Bearer $validAccess') {
      return json({'detail': 'Not authenticated'}, 401);
    }

    if (path == '/users/me') return json(_user);
    if (path == '/models') {
      return json({
        'models': [
          {
            'key': 'echo:echo-1',
            'provider': 'echo',
            'model': 'echo-1',
            'display_name': 'Echo',
            'capabilities': ['chat'],
            'cost_tier': 0,
            'context_window': 8000,
          },
        ],
        'default_policy': 'balanced',
        'greeting': "Hello! I'm Dhanz, your personal AI assistant. How can I help you today?",
      });
    }
    if (path == '/conversations' && req.method == 'POST') {
      final c = _conversation();
      conversations[c['id'] as String] = c;
      return json(c, 201);
    }
    if (path == '/conversations' && req.method == 'GET') {
      final items = conversations.values.map((c) => {...c}..remove('messages')).toList();
      return json({'items': items, 'total': items.length});
    }
    final match = RegExp(r'^/conversations/([^/]+)(/messages|/regenerate)?$').firstMatch(path);
    if (match != null) {
      final c = conversations[match.group(1)];
      if (c == null) return json({'detail': 'Conversation not found'}, 404);
      if (match.group(2) == '/messages') return _stream(c, body['content'] as String);
      if (req.method == 'GET') return json(c);
      if (req.method == 'DELETE') {
        conversations.remove(c['id']);
        return json(null, 204);
      }
    }
    return json({'detail': 'Not found'}, 404);
  }

  Map<String, dynamic> _conversation() {
    final now = DateTime.now().toUtc().toIso8601String();
    return {
      'id': _id(),
      'title': 'New conversation',
      'pinned': false,
      'created_at': now,
      'updated_at': now,
      'messages': <Object>[],
    };
  }

  Map<String, dynamic> _message(String role, String content, {String? model}) => {
    'id': _id(),
    'role': role,
    'content': content,
    'status': 'complete',
    'provider': model == null ? null : 'echo',
    'model': model,
    'input_tokens': null,
    'output_tokens': null,
    'error': null,
    'created_at': DateTime.now().toUtc().toIso8601String(),
  };

  http.StreamedResponse _stream(Map<String, dynamic> conv, String content) {
    final user = _message('user', content);
    final assistant = _message('assistant', reply, model: 'echo-1');
    (conv['messages'] as List<Object>).addAll([user, assistant]);
    conv['title'] = content;
    String ev(String type, Map<String, dynamic> data) =>
        'event: $type\ndata: ${jsonEncode({'type': type, ...data})}\n\n';
    final words = reply.split(' ');
    final chunks = <String>[
      ev('meta', {'conversation_id': conv['id'], 'assistant_message_id': assistant['id'], 'user_message': user}),
      ev('model', {'provider': 'echo', 'model': 'echo-1'}),
      for (var i = 0; i < words.length; i++) ev('delta', {'text': i == 0 ? words[i] : ' ${words[i]}'}),
      ev('done', {'message': assistant}),
    ];
    return http.StreamedResponse(
      Stream.fromIterable(chunks.map(utf8.encode)),
      200,
      headers: {'content-type': 'text/event-stream'},
    );
  }
}
