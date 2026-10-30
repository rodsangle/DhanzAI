import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../../models/models.dart';
import '../config.dart';
import '../storage/secure_store.dart';
import 'sse.dart';

class ApiException implements Exception {
  ApiException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  bool get isUnauthorized => statusCode == 401;

  @override
  String toString() => message;
}

typedef ClientFactory = http.Client Function();

/// HTTP client for the DHANZ AI backend.
///
/// Attaches the access token, transparently refreshes it once on a 401, and
/// calls [onSessionExpired] when the refresh token is no longer valid.
class ApiClient {
  ApiClient({required this.store, required this.baseUrl, ClientFactory? clientFactory})
    : _clientFactory = clientFactory ?? http.Client.new {
    _client = _clientFactory();
  }

  final SecureStore store;
  String baseUrl;
  final ClientFactory _clientFactory;
  late final http.Client _client;
  void Function()? onSessionExpired;
  Future<bool>? _refreshing;

  Uri _uri(String path, [Map<String, String>? query]) =>
      Uri.parse('${baseUrl.replaceAll(RegExp(r'/+$'), '')}${AppConfig.apiPrefix}$path')
          .replace(queryParameters: query?.isEmpty ?? true ? null : query);

  Future<Map<String, String>> _headers({bool auth = true}) async {
    final headers = {'Content-Type': 'application/json', 'Accept': 'application/json'};
    if (auth) {
      final token = await store.read(StoreKeys.accessToken);
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

  // ---- auth --------------------------------------------------------------

  Future<AuthTokens> register(String email, String password, String displayName) async {
    final body = await _json(
      'POST',
      '/auth/register',
      body: {'email': email, 'password': password, 'display_name': displayName},
      auth: false,
    );
    return _saveTokens(AuthTokens.fromJson(body as Map<String, dynamic>));
  }

  Future<AuthTokens> login(String email, String password) async {
    final body = await _json('POST', '/auth/login', body: {'email': email, 'password': password}, auth: false);
    return _saveTokens(AuthTokens.fromJson(body as Map<String, dynamic>));
  }

  Future<void> logout() async {
    final refresh = await store.read(StoreKeys.refreshToken);
    if (refresh != null) {
      try {
        await _json('POST', '/auth/logout', body: {'refresh_token': refresh}, auth: false);
      } on Exception {
        // Best effort: local sign-out must succeed even when offline.
      }
    }
    await clearTokens();
  }

  Future<void> clearTokens() async {
    await store.write(StoreKeys.accessToken, null);
    await store.write(StoreKeys.refreshToken, null);
  }

  Future<bool> hasSession() async => await store.read(StoreKeys.refreshToken) != null;

  Future<AuthTokens> _saveTokens(AuthTokens t) async {
    await store.write(StoreKeys.accessToken, t.accessToken);
    await store.write(StoreKeys.refreshToken, t.refreshToken);
    return t;
  }

  /// Single-flight refresh so parallel 401s trigger only one rotation.
  Future<bool> _refresh() {
    return _refreshing ??= () async {
      try {
        final refresh = await store.read(StoreKeys.refreshToken);
        if (refresh == null) return false;
        final res = await _client.post(
          _uri('/auth/refresh'),
          headers: await _headers(auth: false),
          body: jsonEncode({'refresh_token': refresh}),
        );
        if (res.statusCode != 200) {
          await clearTokens();
          onSessionExpired?.call();
          return false;
        }
        await _saveTokens(AuthTokens.fromJson(jsonDecode(res.body) as Map<String, dynamic>));
        return true;
      } finally {
        _refreshing = null;
      }
    }();
  }

  // ---- generic request helpers -----------------------------------------

  Future<http.Response> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool auth = true,
    bool retry = true,
  }) async {
    final req = http.Request(method, _uri(path, query))..headers.addAll(await _headers(auth: auth));
    if (body != null) req.body = jsonEncode(body);
    final http.Response res;
    try {
      res = await http.Response.fromStream(await _client.send(req));
    } on http.ClientException catch (e) {
      throw ApiException(0, 'Cannot reach the DHANZ AI server at $baseUrl (${e.message}).');
    }
    if (res.statusCode == 401 && auth && retry && await _refresh()) {
      return _send(method, path, body: body, query: query, auth: auth, retry: false);
    }
    return res;
  }

  Future<http.Response> _sendMultipart(
    String path,
    String field,
    String filename,
    Uint8List bytes, {
    Map<String, String> fields = const {},
    String? contentType,
    bool retry = true,
  }) async {
    final req = http.MultipartRequest('POST', _uri(path))
      ..fields.addAll(fields)
      ..files.add(
        http.MultipartFile.fromBytes(
          field,
          bytes,
          filename: filename,
          contentType: contentType == null ? null : MediaType.parse(contentType),
        ),
      );
    final token = await store.read(StoreKeys.accessToken);
    if (token != null) req.headers['Authorization'] = 'Bearer $token';
    final http.Response res;
    try {
      res = await http.Response.fromStream(await _client.send(req));
    } on http.ClientException catch (e) {
      throw ApiException(0, 'Cannot reach the DHANZ AI server at $baseUrl (${e.message}).');
    }
    if (res.statusCode == 401 && retry && await _refresh()) {
      return _sendMultipart(path, field, filename, bytes, fields: fields, contentType: contentType, retry: false);
    }
    return res;
  }

  Future<Object?> _json(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool auth = true,
  }) async {
    final res = await _send(method, path, body: body, query: query, auth: auth);
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    if (res.body.isEmpty) return null;
    return jsonDecode(utf8.decode(res.bodyBytes));
  }

  static String _errorMessage(int status, String body) {
    try {
      final detail = (jsonDecode(body) as Map<String, dynamic>)['detail'];
      if (detail is String) return detail;
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first as Map<String, dynamic>;
        final field = (first['loc'] as List<dynamic>?)?.last;
        return field == null ? '${first['msg']}' : '$field: ${first['msg']}';
      }
    } on Object {
      // fall through
    }
    return 'Request failed ($status)';
  }

  // ---- users & models ----------------------------------------------------

  Future<Map<String, dynamic>> creativeCapabilities() async =>
      await _json('GET', '/creative/capabilities') as Map<String, dynamic>;

  Future<Map<String, dynamic>> creativeCredits() async =>
      await _json('GET', '/creative/credits') as Map<String, dynamic>;

  Future<List<Map<String, dynamic>>> creations({int offset = 0}) async =>
      (await _json('GET', '/creative/jobs', query: {'offset': '$offset'}) as List).cast<Map<String, dynamic>>();

  Future<Map<String, dynamic>> creativePolicy() async =>
      await _json('GET', '/creative/admin/policy') as Map<String, dynamic>;

  Future<void> updateCreativePolicy(Map<String, dynamic> policy) async =>
      _json('PUT', '/creative/admin/policy', body: policy);

  Future<List<Map<String, dynamic>>> creativeReports() async =>
      (await _json('GET', '/creative/admin/reports') as List).cast<Map<String, dynamic>>();

  Future<void> removeUnsafeCreation(String id) async => _json('DELETE', '/creative/admin/jobs/$id');

  Future<Map<String, dynamic>> generateMedia(Map<String, dynamic> body) async =>
      await _json('POST', '/creative/jobs', body: body) as Map<String, dynamic>;

  Future<void> cancelCreation(String id) async => _json('POST', '/creative/jobs/$id/cancel');

  Future<void> deleteCreation(String id) async => _json('DELETE', '/creative/jobs/$id');

  Future<void> reportCreation(String id, String reason) async =>
      _json('POST', '/creative/jobs/$id/report', body: {'reason': reason});

  Future<String> creationMediaUrl(String id) async {
    final body = await _json('POST', '/creative/jobs/$id/media-link') as Map<String, dynamic>;
    return '${baseUrl.replaceAll(RegExp(r'/+$'), '')}${AppConfig.apiPrefix}${body['path']}';
  }

  Future<Uint8List> downloadCreation(String id) async {
    final response = await _send('GET', '/creative/jobs/$id/download');
    if (response.statusCode >= 400) {
      throw ApiException(response.statusCode, _errorMessage(response.statusCode, response.body));
    }
    return response.bodyBytes;
  }

  Future<User> me() async => User.fromJson(await _json('GET', '/users/me') as Map<String, dynamic>);

  Future<User> updateMe({
    String? displayName,
    String? preferredModel,
    String? routingPolicy,
    bool? autoIndexWeb,
    bool? memoryEnabled,
    int? retentionDays,
  }) async {
    final body = <String, Object?>{
      'display_name': ?displayName,
      'preferred_model': ?preferredModel,
      'routing_policy': ?routingPolicy,
      'auto_index_web': ?autoIndexWeb,
      'memory_enabled': ?memoryEnabled,
      'retention_days': ?retentionDays, // 0 = keep forever
    };
    return User.fromJson(await _json('PATCH', '/users/me', body: body) as Map<String, dynamic>);
  }

  // ---- account security ----------------------------------------------------

  Future<void> changePassword(String currentPassword, String newPassword) =>
      _json('POST', '/users/me/password', body: {'current_password': currentPassword, 'new_password': newPassword});

  Future<List<SessionInfo>> sessions() async => [
    for (final s in await _json('GET', '/users/me/sessions') as List<dynamic>)
      SessionInfo.fromJson(s as Map<String, dynamic>),
  ];

  Future<void> revokeSession(String id) => _json('DELETE', '/users/me/sessions/$id');

  Future<int> revokeOtherSessions() async =>
      (await _json('POST', '/users/me/sessions/revoke-others') as Map<String, dynamic>)['ended'] as int;

  /// Emails a one-time code (the answer is the same whether or not the account exists).
  Future<void> requestPasswordReset(String email) =>
      _json('POST', '/auth/password-reset/request', body: {'email': email}, auth: false);

  Future<void> confirmPasswordReset(String email, String code, String newPassword) => _json(
    'POST',
    '/auth/password-reset/confirm',
    body: {'email': email, 'code': code, 'new_password': newPassword},
    auth: false,
  );

  // ---- administration --------------------------------------------------------

  Future<AdminStats> adminStats() async =>
      AdminStats.fromJson(await _json('GET', '/admin/stats') as Map<String, dynamic>);

  Future<List<AdminUser>> adminUsers({String? query}) async {
    final body = await _json('GET', '/admin/users', query: {'q': ?query}) as Map<String, dynamic>;
    return [for (final u in body['items'] as List<dynamic>) AdminUser.fromJson(u as Map<String, dynamic>)];
  }

  Future<AdminUser> adminUpdateUser(String id, {bool? isActive, String? role}) async => AdminUser.fromJson(
    await _json('PATCH', '/admin/users/$id', body: {'is_active': ?isActive, 'role': ?role}) as Map<String, dynamic>,
  );

  Future<String> exportMyData() async {
    final res = await _send('GET', '/users/me/export');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    return const JsonEncoder.withIndent('  ').convert(jsonDecode(utf8.decode(res.bodyBytes)));
  }

  Future<void> deleteAccount(String password) async {
    await _json('DELETE', '/users/me', body: {'password': password});
    await clearTokens();
  }

  /// Configured models plus optional features (web search, semantic search).
  Future<ServerInfo> serverInfo() async {
    final body = await _json('GET', '/models') as Map<String, dynamic>;
    return (
      models: [for (final m in body['models'] as List<dynamic>) AiModel.fromJson(m as Map<String, dynamic>)],
      features: Features.fromJson(body['features'] as Map<String, dynamic>?),
    );
  }

  // ---- knowledge library -------------------------------------------------

  Future<List<KnowledgeDocument>> documents({String? query}) async {
    final body = await _json(
      'GET',
      '/knowledge/documents',
      query: {if (query != null && query.isNotEmpty) 'q': query, 'limit': '200'},
    ) as Map<String, dynamic>;
    return [for (final d in body['items'] as List<dynamic>) KnowledgeDocument.fromJson(d as Map<String, dynamic>)];
  }

  Future<KnowledgeDocument> document(String id) async =>
      KnowledgeDocument.fromJson(await _json('GET', '/knowledge/documents/$id') as Map<String, dynamic>);

  Future<KnowledgeDocument> addDocument(String url) async => KnowledgeDocument.fromJson(
    await _json('POST', '/knowledge/documents', body: {'url': url}) as Map<String, dynamic>,
  );

  Future<void> deleteDocument(String id) => _json('DELETE', '/knowledge/documents/$id');

  Future<Map<String, dynamic>> researchAndSave(String query, {String? projectId}) async =>
      await _json('POST', '/knowledge/research', body: {'query': query, 'project_id': projectId})
          as Map<String, dynamic>;

  Future<List<LibraryHit>> searchLibrary(String query) async {
    final body = await _json('GET', '/knowledge/search', query: {'q': query}) as List<dynamic>;
    return [for (final h in body) LibraryHit.fromJson(h as Map<String, dynamic>)];
  }

  // ---- conversations -----------------------------------------------------

  Future<List<ConversationSummary>> conversations({String? query, String? projectId}) async {
    final body = await _json(
      'GET',
      '/conversations',
      query: {if (query != null && query.isNotEmpty) 'q': query, 'project_id': ?projectId},
    ) as Map<String, dynamic>;
    return [for (final c in body['items'] as List<dynamic>) ConversationSummary.fromJson(c as Map<String, dynamic>)];
  }

  Future<ConversationSummary> createConversation({String? projectId, bool temporary = false}) async =>
      ConversationSummary.fromJson(
        await _json('POST', '/conversations', body: {'project_id': ?projectId, if (temporary) 'temporary': true})
            as Map<String, dynamic>,
      );

  Future<ConversationDetail> conversation(String id) async =>
      ConversationDetail.fromJson(await _json('GET', '/conversations/$id') as Map<String, dynamic>);

  /// [projectId]: pass a project id to move the chat into it, or '' to remove it from its project.
  Future<ConversationSummary> updateConversation(String id, {String? title, bool? pinned, String? projectId}) async {
    final body = <String, Object?>{
      'title': ?title,
      'pinned': ?pinned,
      if (projectId != null) 'project_id': projectId.isEmpty ? null : projectId,
    };
    return ConversationSummary.fromJson(await _json('PATCH', '/conversations/$id', body: body) as Map<String, dynamic>);
  }

  Future<void> deleteConversation(String id) => _json('DELETE', '/conversations/$id');

  Future<String> exportConversation(String id, {String format = 'markdown'}) async =>
      utf8.decode(await exportConversationBytes(id, format: format));

  /// Raw export (markdown, txt or pdf) for saving to a file.
  Future<Uint8List> exportConversationBytes(String id, {String format = 'markdown'}) async {
    final res = await _send('GET', '/conversations/$id/export', query: {'format': format});
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    return res.bodyBytes;
  }

  // ---- files -------------------------------------------------------------

  /// Uploads a document or image; it is scanned, its text extracted and indexed by the server.
  Future<KnowledgeDocument> uploadFile(String filename, Uint8List bytes, {String? projectId}) async {
    final res = await _sendMultipart('/files', 'file', filename, bytes, fields: {'project_id': ?projectId});
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    return KnowledgeDocument.fromJson(jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>);
  }

  Future<Uint8List> downloadFile(String documentId) async {
    final res = await _send('GET', '/files/$documentId/download');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    return res.bodyBytes;
  }

  Future<KnowledgeDocument> moveDocument(String documentId, String? projectId) async => KnowledgeDocument.fromJson(
    await _json('PATCH', '/knowledge/documents/$documentId', body: {'project_id': projectId}) as Map<String, dynamic>,
  );

  // ---- projects ----------------------------------------------------------

  Future<List<Project>> projects() async => [
    for (final p in await _json('GET', '/projects') as List<dynamic>) Project.fromJson(p as Map<String, dynamic>),
  ];

  Future<Project> createProject(String name, {String? description, String? instructions}) async => Project.fromJson(
    await _json('POST', '/projects', body: {'name': name, 'description': ?description, 'instructions': ?instructions})
        as Map<String, dynamic>,
  );

  Future<Project> updateProject(String id, {String? name, String? description, String? instructions}) async =>
      Project.fromJson(
        await _json(
          'PATCH',
          '/projects/$id',
          body: {'name': ?name, 'description': ?description, 'instructions': ?instructions},
        ) as Map<String, dynamic>,
      );

  Future<void> deleteProject(String id) => _json('DELETE', '/projects/$id');

  // ---- memory ------------------------------------------------------------

  Future<List<Memory>> memories() async => [
    for (final m in await _json('GET', '/memories') as List<dynamic>) Memory.fromJson(m as Map<String, dynamic>),
  ];

  Future<Memory> addMemory(String content) async =>
      Memory.fromJson(await _json('POST', '/memories', body: {'content': content}) as Map<String, dynamic>);

  Future<Memory> editMemory(String id, String content) async =>
      Memory.fromJson(await _json('PATCH', '/memories/$id', body: {'content': content}) as Map<String, dynamic>);

  Future<void> deleteMemory(String id) => _json('DELETE', '/memories/$id');

  Future<void> deleteAllMemories() => _json('DELETE', '/memories');

  // ---- voice -------------------------------------------------------------

  Future<String> transcribe(Uint8List audio, {String filename = 'speech.m4a', String? language}) async {
    final res = await _sendMultipart(
      '/voice/transcribe',
      'audio',
      filename,
      audio,
      contentType: 'audio/m4a',
      fields: {'language': ?language},
    );
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    return (jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>)['text'] as String;
  }

  // ---- reminders -------------------------------------------------------------

  Future<List<Reminder>> reminders({bool includeDone = false}) async => [
    for (final r in await _json('GET', '/reminders', query: {if (includeDone) 'include_done': 'true'}) as List<dynamic>)
      Reminder.fromJson(r as Map<String, dynamic>),
  ];

  Future<Reminder> createReminder(String text, DateTime dueAt) async => Reminder.fromJson(
    await _json('POST', '/reminders', body: {'text': text, 'due_at': clientTimeNow(dueAt)}) as Map<String, dynamic>,
  );

  Future<Reminder> updateReminder(String id, {bool? done, DateTime? dueAt, String? text}) async => Reminder.fromJson(
    await _json(
      'PATCH',
      '/reminders/$id',
      body: {'done': ?done, 'text': ?text, if (dueAt != null) 'due_at': clientTimeNow(dueAt)},
    ) as Map<String, dynamic>,
  );

  Future<void> deleteReminder(String id) => _json('DELETE', '/reminders/$id');

  /// The reminder as an .ics file for calendar apps.
  Future<Uint8List> reminderCalendarFile(String id) async {
    final res = await _send('GET', '/reminders/$id/calendar.ics');
    if (res.statusCode >= 400) throw ApiException(res.statusCode, _errorMessage(res.statusCode, res.body));
    return res.bodyBytes;
  }

  // ---- devices & updates ---------------------------------------------------

  /// Registers this phone for "your answer is ready" notifications. [platform] is android or ios.
  Future<void> registerDevice(String platform, String token, {String? appVersion}) =>
      _json('POST', '/devices', body: {'platform': platform, 'token': token, 'app_version': ?appVersion});

  Future<void> unregisterDevice(String token) => _json('POST', '/devices/unregister', body: {'token': token});

  Future<UpdateInfo> checkForUpdate(String platform, String version) async => UpdateInfo.fromJson(
    await _json('GET', '/app/updates', query: {'platform': platform, 'version': version}, auth: false)
        as Map<String, dynamic>,
  );

  // ---- streaming chat ----------------------------------------------------

  /// Stops the reply being generated in [conversationId]. The partial text is kept as "stopped".
  Future<void> stopReply(String conversationId) => _json('POST', '/conversations/$conversationId/stop');

  /// Opens a streaming chat request. The reply keeps generating on the server if the connection
  /// drops (use [stopReply] to stop it); cancelling the [ChatStream] only stops listening.
  Future<ChatStream> streamChat(
    String conversationId, {
    String? content,
    String? editMessageId,
    String? modelKey,
    bool? web,
    List<String> attachmentIds = const [],
    bool regenerate = false,
  }) async {
    final parts = modelKey?.split(':');
    final body = <String, Object?>{
      'content': ?content,
      'edit_message_id': ?editMessageId,
      'web': ?web,
      if (attachmentIds.isNotEmpty) 'attachment_ids': attachmentIds,
      'client_time': clientTimeNow(),
      if (parts != null && parts.length >= 2) 'provider': parts.first,
      if (parts != null && parts.length >= 2) 'model': parts.sublist(1).join(':'),
    };
    final path = '/conversations/$conversationId/${regenerate ? 'regenerate' : 'messages'}';

    Future<http.StreamedResponse> open(http.Client client) async {
      final req = http.Request('POST', _uri(path))
        ..headers.addAll(await _headers())
        ..headers['Accept'] = 'text/event-stream'
        ..body = jsonEncode(body);
      try {
        return await client.send(req);
      } on http.ClientException catch (e) {
        client.close();
        throw ApiException(0, 'Cannot reach the DHANZ AI server at $baseUrl (${e.message}).');
      }
    }

    // A dedicated client per stream, so it can be closed without affecting other requests.
    var client = _clientFactory();
    var res = await open(client);
    if (res.statusCode == 401 && await _refresh()) {
      client.close();
      client = _clientFactory();
      res = await open(client);
    }
    if (res.statusCode != 200) {
      final text = await res.stream.bytesToString();
      client.close();
      throw ApiException(res.statusCode, _errorMessage(res.statusCode, text));
    }
    return ChatStream(decodeSse(res.stream), client);
  }

  void close() => _client.close();
}

typedef ServerInfo = ({List<AiModel> models, Features features});

class ChatStream {
  ChatStream(this.events, this._client);

  final Stream<ChatEvent> events;
  final http.Client _client;

  void cancel() => _client.close();
}
