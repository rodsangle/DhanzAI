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
  final documents = <Map<String, dynamic>>[];
  final uploads = <String>[]; // raw multipart bodies
  final projects = <Map<String, dynamic>>[];
  final memories = <Map<String, dynamic>>[];
  final conversationBodies = <Map<String, dynamic>>[];
  String transcript = 'Hey Dhanz, what is the capital of France?';
  final chatBodies = <Map<String, dynamic>>[];

  /// Simulates the connection dropping right after the reply started: the reply stays "streaming"
  /// on the server until the test finishes it.
  bool dropAfterMeta = false;
  bool pushNotifications = false;
  final devices = <String, Map<String, dynamic>>{};
  final passwords = <String, String>{};
  final sessions = <Map<String, dynamic>>[
    {
      'id': 'session-this',
      'user_agent': 'DhanzAI Windows',
      'created_at': '2026-10-01T10:00:00Z',
      'last_used_at': '2026-10-29T10:00:00Z',
      'current': true,
    },
    {
      'id': 'session-phone',
      'user_agent': 'Dart/3.10 (dart:io) android',
      'created_at': '2026-10-02T10:00:00Z',
      'last_used_at': '2026-10-28T10:00:00Z',
      'current': false,
    },
  ];
  static const resetCode = 'ABCDE-23456';

  /// Tool activity the next reply reports (as the real server does after running tools).
  List<Map<String, dynamic>> toolActivity = [];
  final reminders = <Map<String, dynamic>>[];
  int calendarDownloads = 0;
  String? resetRequestedFor;
  Map<String, dynamic> updateInfo = {
    'platform': 'windows',
    'current_version': '0.0.0',
    'latest_version': null,
    'update_available': false,
  };

  static const source = {
    'n': 1,
    'title': '2nm chips arrive',
    'url': 'https://chips.example/2nm',
    'site_name': 'Chip Times',
    'published_at': '2026-10-20T09:00:00+00:00',
    'retrieved_at': '2026-10-28T10:00:00+00:00',
    'origin': 'web',
  };

  // ---- public accounts: email codes, two-step verification, Google/Apple -------------------------
  Map<String, dynamic> authOptions = {'registration_open': true, 'password_reset': true};
  static const emailCode = '482913';
  static const mfaCode = '123456';
  static const recoveryCode = 'AAAA-BBBB-CCCC';
  static const googleToken = 'google-id-token-abc';
  final oauthBodies = <Map<String, dynamic>>[];
  final identities = <Map<String, dynamic>>[];
  Map<String, dynamic>? deleteBody;

  String _id() => 'id-${_ids++}';

  Map<String, dynamic>? _current;

  Map<String, dynamic> get _user => _current ?? users.values.first;

  Map<String, dynamic> _signIn(Map<String, dynamic> user) => user['mfa_enabled'] == true
      ? {'mfa_required': true, 'mfa_token': 'mfa-${user['email']}', 'expires_in': 300}
      : _tokensFor(user);

  Map<String, dynamic> _tokensFor(Map<String, dynamic> user) {
    _current = user;
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
    final bytes = await bodyStream.toBytes();
    final isMultipart = (req.headers['content-type'] ?? '').startsWith('multipart/');
    final bodyText = isMultipart ? '' : utf8.decode(bytes);
    final body = bodyText.isEmpty ? <String, dynamic>{} : jsonDecode(bodyText) as Map<String, dynamic>;
    if (isMultipart) uploads.add(latin1.decode(bytes));
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
        'role': users.isEmpty ? 'admin' : 'user', // the first account administers the server
        'routing_policy': 'balanced',
        'preferred_model': null,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      };
      users[user['email'] as String] = user;
      passwords[user['email'] as String] = body['password'] as String;
      return json(_tokensFor(user), 201);
    }
    if (path == '/auth/login') {
      final user = users[(body['email'] as String).toLowerCase()];
      if (user == null || passwords[user['email']] != body['password']) {
        return json({'detail': 'Invalid email or password'}, 401);
      }
      return json(_signIn(user));
    }
    if (path == '/auth/options') return json(authOptions);
    if (path == '/auth/mfa/verify') {
      final email = (body['mfa_token'] as String).replaceFirst('mfa-', '');
      final user = users[email];
      final code = (body['code'] as String).toUpperCase();
      if (user == null || (code != mfaCode && code != recoveryCode)) {
        return json({'detail': 'That code is not correct. Check the time on your phone.'}, 401);
      }
      return json(_tokensFor(user));
    }
    if (path.startsWith('/auth/oauth/')) {
      oauthBodies.add(body);
      final provider = path.split('/').last;
      if (body['id_token'] != googleToken) return json({'detail': 'The sign-in token is not valid.'}, 401);
      final user = users.putIfAbsent(
        'ada@gmail.com',
        () => {
          'id': _id(),
          'email': 'ada@gmail.com',
          'display_name': body['display_name'] ?? 'Ada Lovelace',
          'role': users.isEmpty ? 'admin' : 'user',
          'routing_policy': 'balanced',
          'preferred_model': null,
          'email_verified': true,
          'has_password': false,
          'mfa_enabled': false,
          'created_at': DateTime.now().toUtc().toIso8601String(),
        },
      );
      if (!identities.any((i) => i['provider'] == provider)) {
        identities.add({
          'provider': provider,
          'email': 'ada@gmail.com',
          'created_at': '2026-10-29T10:00:00Z',
          'last_used_at': '2026-10-29T10:00:00Z',
        });
      }
      return json(_signIn(user));
    }
    if (path == '/auth/refresh') {
      if (body['refresh_token'] != validRefresh) return json({'detail': 'Session expired'}, 401);
      return json(_tokensFor(_user));
    }
    if (path == '/auth/logout') return json(null, 204);
    if (path == '/auth/password-reset/request') {
      resetRequestedFor = (body['email'] as String).toLowerCase();
      return json({'detail': 'If an account exists for this email, a reset code has been sent.'}, 202);
    }
    if (path == '/auth/password-reset/confirm') {
      final email = (body['email'] as String).toLowerCase();
      if (body['code'] != resetCode || !users.containsKey(email)) {
        return json({'detail': 'The code is invalid or has expired. Request a new one.'}, 400);
      }
      passwords[email] = body['new_password'] as String;
      return json(null, 204);
    }
    if (path == '/app/updates') return json({...updateInfo, 'current_version': req.url.queryParameters['version']});

    if (req.headers['Authorization'] != 'Bearer $validAccess') {
      return json({'detail': 'Not authenticated'}, 401);
    }

    if (path == '/reminders' && req.method == 'GET') {
      final all = req.url.queryParameters['include_done'] == 'true';
      return json([
        for (final r in reminders)
          if (all || r['done_at'] == null) r,
      ]);
    }
    if (path == '/reminders' && req.method == 'POST') {
      final r = {
        'id': _id(),
        'text': body['text'],
        'due_at': body['due_at'],
        'duration_minutes': null,
        'location': null,
        'conversation_id': null,
        'notified_at': null,
        'done_at': null,
        'created_at': DateTime.now().toUtc().toIso8601String(),
      };
      reminders.add(r);
      return json(r, 201);
    }
    final reminderMatch = RegExp(r'^/reminders/([^/]+)(/calendar\.ics)?$').firstMatch(path);
    if (reminderMatch != null) {
      final r = reminders.where((x) => x['id'] == reminderMatch.group(1)).firstOrNull;
      if (r == null) return json({'detail': 'Reminder not found'}, 404);
      if (reminderMatch.group(2) != null) {
        calendarDownloads++;
        return http.StreamedResponse(
          Stream.value(utf8.encode('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n')),
          200,
          headers: {'content-type': 'text/calendar'},
        );
      }
      if (req.method == 'DELETE') {
        reminders.remove(r);
        return json(null, 204);
      }
      if (body.containsKey('done')) {
        r['done_at'] = body['done'] == true ? DateTime.now().toUtc().toIso8601String() : null;
      }
      r['done_at'] = body['done'] == true ? DateTime.now().toUtc().toIso8601String() : null;
      return json(r);
    }
    if (path == '/users/me/password') {
      if (passwords[_user['email']] != body['current_password']) {
        return json({'detail': 'Current password is incorrect'}, 403);
      }
      passwords[_user['email'] as String] = body['new_password'] as String;
      sessions.removeWhere((x) => x['current'] != true);
      return json(null, 204);
    }
    if (path == '/users/me/sessions') return json(sessions);
    if (path == '/users/me/email-verification') return json({'detail': 'We sent a code.'}, 202);
    if (path == '/users/me/email-verification/confirm') {
      if (body['code'] != emailCode) {
        return json({'detail': 'The code is invalid or has expired. Request a new one.'}, 400);
      }
      _user['email_verified'] = true;
      return json(_user);
    }
    if (path == '/users/me/mfa/setup') {
      if (_user['has_password'] != false && passwords[_user['email']] != body['password']) {
        return json({'detail': 'Password is incorrect'}, 403);
      }
      return json({
        'secret': 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP',
        'otpauth_uri': 'otpauth://totp/DHANZ%20AI%3Aada?secret=JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP&issuer=DHANZ%20AI',
      });
    }
    if (path == '/users/me/mfa/enable') {
      if (body['code'] != mfaCode) return json({'detail': 'That code is not correct.'}, 400);
      _user['mfa_enabled'] = true;
      return json({
        'recovery_codes': [recoveryCode, 'DDDD-EEEE-FFFF'],
      });
    }
    if (path == '/users/me/mfa/disable') {
      if (body['code'] != mfaCode) return json({'detail': 'That code is not correct'}, 403);
      _user['mfa_enabled'] = false;
      return json(_user);
    }
    if (path == '/users/me/identities') return json(identities);
    if (path.startsWith('/users/me/identities/') && req.method == 'DELETE') {
      if (_user['has_password'] == false && identities.length == 1) {
        return json({'detail': 'This is your only way to sign in. Set a password first.'}, 409);
      }
      identities.removeWhere((i) => i['provider'] == path.split('/').last);
      return json(null, 204);
    }
    if (path == '/users/me' && req.method == 'DELETE') {
      deleteBody = body;
      users.remove(_user['email']);
      _current = null;
      return json(null, 204);
    }
    if (path == '/users/me/sessions/revoke-others') {
      final ended = sessions.where((x) => x['current'] != true).length;
      sessions.removeWhere((x) => x['current'] != true);
      return json({'ended': ended});
    }
    if (path.startsWith('/users/me/sessions/') && req.method == 'DELETE') {
      sessions.removeWhere((x) => x['id'] == path.split('/').last);
      return json(null, 204);
    }
    if (path.startsWith('/admin/') && _user['role'] != 'admin') {
      return json({'detail': 'Administrator access required'}, 403);
    }
    if (path == '/admin/stats') {
      return json({
        'users': users.length,
        'active_users_7d': 1,
        'conversations': conversations.length,
        'messages_24h': chatBodies.length,
        'replies_failed_24h': 0,
        'documents': documents.length,
        'usage_30d': [
          {'provider': 'echo', 'replies': chatBodies.length, 'input_tokens': 1200, 'output_tokens': 3400},
        ],
      });
    }
    if (path == '/admin/users') {
      final q = req.url.queryParameters['q']?.toLowerCase();
      final items = [
        for (final u in users.values)
          if (q == null || (u['email'] as String).contains(q))
            {...u, 'is_active': u['is_active'] ?? true, 'conversations': 0, 'messages_30d': 0},
      ];
      return json({'items': items, 'total': items.length});
    }
    if (path.startsWith('/admin/users/') && req.method == 'PATCH') {
      final u = users.values.firstWhere((x) => x['id'] == path.split('/').last);
      if (body.containsKey('is_active')) u['is_active'] = body['is_active'];
      if (body.containsKey('role')) u['role'] = body['role'];
      return json({...u, 'is_active': u['is_active'] ?? true});
    }
    if (path == '/users/me' && req.method == 'PATCH') {
      if (body.containsKey('retention_days')) {
        _user['retention_days'] = body['retention_days'] == 0 ? null : body['retention_days'];
      }
      if (body.containsKey('memory_enabled')) _user['memory_enabled'] = body['memory_enabled'];
      return json(_user);
    }
    if (path == '/users/me') return json(_user);
    if (path == '/files' && req.method == 'POST') {
      final raw = uploads.last;
      final name = RegExp(r'filename="([^"]+)"').firstMatch(raw)?.group(1) ?? 'file';
      final projectId = RegExp(r'name="project_id"\r\n\r\n([^\r]+)').firstMatch(raw)?.group(1);
      final now = DateTime.now().toUtc().toIso8601String();
      final doc = {
        'id': _id(),
        'kind': 'file',
        'url': 'upload:x',
        'title': name,
        'site_name': null,
        'author': null,
        'published_at': null,
        'retrieved_at': now,
        'added_via': 'upload',
        'project_id': projectId,
        'file_type': name.endsWith('.png') ? 'image' : 'pdf',
        'mime_type': 'application/pdf',
        'size_bytes': 1234,
        'scan_status': 'not_scanned',
        'notes': null,
        'created_at': now,
      };
      documents.insert(0, doc);
      return json(doc, 201);
    }
    if (path == '/projects' && req.method == 'GET') return json(projects);
    if (path == '/projects' && req.method == 'POST') {
      final now = DateTime.now().toUtc().toIso8601String();
      final p = {
        'id': _id(),
        'name': body['name'],
        'description': body['description'],
        'instructions': body['instructions'],
        'created_at': now,
        'updated_at': now,
      };
      projects.add(p);
      return json(p, 201);
    }
    if (path == '/memories' && req.method == 'GET') return json(memories);
    if (path == '/memories' && req.method == 'POST') {
      final now = DateTime.now().toUtc().toIso8601String();
      final m = {'id': _id(), 'content': body['content'], 'source': 'manual', 'created_at': now, 'updated_at': now};
      memories.add(m);
      return json(m, 201);
    }
    if (path == '/voice/transcribe') return json({'text': transcript});
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
        'features': {
          'web_search': true,
          'semantic_search': false,
          'speech_to_text': true,
          'vision': true,
          'push_notifications': pushNotifications,
        },
        'greeting': "Hello! I'm Dhanz, your personal AI assistant. How can I help you today?",
      });
    }
    if (path == '/conversations' && req.method == 'POST') {
      conversationBodies.add(body);
      final c = _conversation()
        ..['project_id'] = body['project_id']
        ..['temporary'] = body['temporary'] ?? false;
      conversations[c['id'] as String] = c;
      return json(c, 201);
    }
    if (path == '/conversations' && req.method == 'GET') {
      final items = conversations.values.map((c) => {...c}..remove('messages')).toList();
      return json({'items': items, 'total': items.length});
    }
    if (path == '/devices') {
      devices[body['token'] as String] = body;
      return json(null, 204);
    }
    if (path == '/devices/unregister') {
      devices.remove(body['token']);
      return json(null, 204);
    }
    final match = RegExp(r'^/conversations/([^/]+)(/messages|/regenerate|/stop)?$').firstMatch(path);
    if (match != null) {
      final c = conversations[match.group(1)];
      if (c == null) return json({'detail': 'Conversation not found'}, 404);
      if (match.group(2) == '/stop') {
        final running = (c['messages'] as List<Object>).cast<Map<String, dynamic>>().where(
          (m) => m['status'] == 'streaming',
        );
        final id = running.isEmpty ? null : running.last['id'];
        for (final m in running) {
          m['status'] = 'stopped';
        }
        return json({'stopping': id}, 202);
      }
      if (match.group(2) == '/messages') {
        chatBodies.add(body);
        return _stream(
          c,
          body['content'] as String,
          research: body['web'] == true,
          attachmentIds: (body['attachment_ids'] as List<dynamic>?)?.cast<String>() ?? const [],
        );
      }
      if (req.method == 'GET') return json(c);
      if (req.method == 'DELETE') {
        conversations.remove(c['id']);
        return json(null, 204);
      }
    }
    if (path == '/knowledge/documents' && req.method == 'GET') {
      return json({'items': documents, 'total': documents.length});
    }
    if (path == '/knowledge/documents' && req.method == 'POST') {
      final url = body['url'] as String;
      if (url.contains('blocked')) {
        return json({'detail': "Could not add this page: the site's robots.txt does not allow automated reading"}, 422);
      }
      final now = DateTime.now().toUtc().toIso8601String();
      final doc = {
        'id': _id(),
        'kind': 'web',
        'url': url,
        'title': 'Growing tomatoes',
        'site_name': 'Garden Weekly',
        'author': null,
        'published_at': null,
        'retrieved_at': now,
        'added_via': 'manual',
        'created_at': now,
      };
      documents.insert(0, doc);
      return json(doc, 201);
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

  /// The server finished the reply that [dropAfterMeta] left running.
  void finishRunningReplies() {
    for (final c in conversations.values) {
      for (final m in (c['messages'] as List<Object>).cast<Map<String, dynamic>>()) {
        if (m['status'] == 'streaming') {
          m
            ..['status'] = 'complete'
            ..['content'] = reply;
        }
      }
    }
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

  http.StreamedResponse _stream(
    Map<String, dynamic> conv,
    String content, {
    bool research = false,
    List<String> attachmentIds = const [],
  }) {
    final user = _message('user', content);
    if (attachmentIds.isNotEmpty) {
      user['attachments'] = [
        for (final id in attachmentIds)
          {
            'id': id,
            'filename': documents.firstWhere((d) => d['id'] == id)['title'],
            'file_type': documents.firstWhere((d) => d['id'] == id)['file_type'],
          },
      ];
    }
    final remember = RegExp(r'^remember that (.+?)\.?$', caseSensitive: false).firstMatch(content);
    final assistant = _message('assistant', reply, model: 'echo-1');
    final activity = toolActivity;
    toolActivity = [];
    if (activity.isNotEmpty) assistant['tool_activity'] = activity;
    if (research) assistant['citations'] = [source];
    (conv['messages'] as List<Object>).addAll([user, assistant]);
    if (dropAfterMeta) {
      assistant
        ..['status'] = 'streaming'
        ..['content'] = '';
      final controller = StreamController<List<int>>();
      controller.add(
        utf8.encode(
          'event: meta\ndata: ${jsonEncode({'type': 'meta', 'conversation_id': conv['id'], 'assistant_message_id': assistant['id'], 'user_message': user})}\n\n',
        ),
      );
      Timer.run(() {
        controller.addError(http.ClientException('Connection closed'));
        unawaited(controller.close());
      });
      return http.StreamedResponse(controller.stream, 200, headers: {'content-type': 'text/event-stream'});
    }
    conv['title'] = content;
    String ev(String type, Map<String, dynamic> data) =>
        'event: $type\ndata: ${jsonEncode({'type': type, ...data})}\n\n';
    final words = reply.split(' ');
    final chunks = <String>[
      ev('meta', {'conversation_id': conv['id'], 'assistant_message_id': assistant['id'], 'user_message': user}),
      if (research) ...[
        ev('research', {'stage': 'searching', 'query': content}),
        ev('research', {
          'stage': 'reading',
          'urls': [source['url']],
        }),
        ev('research', {
          'stage': 'sources',
          'sources': [source],
        }),
      ],
      if (remember != null) ev('memory', {'action': 'saved', 'content': remember.group(1)}),
      ev('model', {'provider': 'echo', 'model': 'echo-1'}),
      if (activity.isNotEmpty) ...[
        ev('tool', {
          'stage': 'running',
          'labels': ['Setting a reminder'],
        }),
        ev('tool', {'stage': 'done', 'activity': activity}),
      ],
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
