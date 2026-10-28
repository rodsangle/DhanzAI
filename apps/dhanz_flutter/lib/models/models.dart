/// Data classes mirroring the backend API (see backend/app/schemas).
library;

DateTime _date(Object? v) => DateTime.parse(v! as String).toLocal();

class User {
  const User({
    required this.id,
    required this.email,
    required this.displayName,
    required this.role,
    required this.routingPolicy,
    this.preferredModel,
  });

  factory User.fromJson(Map<String, dynamic> j) => User(
    id: j['id'] as String,
    email: j['email'] as String,
    displayName: j['display_name'] as String,
    role: j['role'] as String,
    routingPolicy: j['routing_policy'] as String,
    preferredModel: j['preferred_model'] as String?,
  );

  final String id;
  final String email;
  final String displayName;
  final String role;
  final String routingPolicy;
  final String? preferredModel;
}

class AuthTokens {
  const AuthTokens({required this.accessToken, required this.refreshToken, required this.user});

  factory AuthTokens.fromJson(Map<String, dynamic> j) => AuthTokens(
    accessToken: j['access_token'] as String,
    refreshToken: j['refresh_token'] as String,
    user: User.fromJson(j['user'] as Map<String, dynamic>),
  );

  final String accessToken;
  final String refreshToken;
  final User user;
}

class ConversationSummary {
  const ConversationSummary({required this.id, required this.title, required this.pinned, required this.updatedAt});

  factory ConversationSummary.fromJson(Map<String, dynamic> j) => ConversationSummary(
    id: j['id'] as String,
    title: j['title'] as String,
    pinned: j['pinned'] as bool,
    updatedAt: _date(j['updated_at']),
  );

  final String id;
  final String title;
  final bool pinned;
  final DateTime updatedAt;
}

enum MessageStatus { streaming, complete, error, stopped }

class ChatMessage {
  const ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.status,
    this.provider,
    this.model,
    this.error,
  });

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
    id: j['id'] as String,
    role: j['role'] as String,
    content: j['content'] as String,
    status: MessageStatus.values.asNameMap()[j['status']] ?? MessageStatus.complete,
    provider: j['provider'] as String?,
    model: j['model'] as String?,
    error: j['error'] as String?,
  );

  final String id;
  final String role;
  final String content;
  final MessageStatus status;
  final String? provider;
  final String? model;
  final String? error;

  bool get isUser => role == 'user';

  ChatMessage copyWith({String? content, MessageStatus? status, String? provider, String? model, String? error}) =>
      ChatMessage(
        id: id,
        role: role,
        content: content ?? this.content,
        status: status ?? this.status,
        provider: provider ?? this.provider,
        model: model ?? this.model,
        error: error ?? this.error,
      );
}

class ConversationDetail {
  const ConversationDetail({required this.summary, required this.messages});

  factory ConversationDetail.fromJson(Map<String, dynamic> j) => ConversationDetail(
    summary: ConversationSummary.fromJson(j),
    messages: [for (final m in j['messages'] as List<dynamic>) ChatMessage.fromJson(m as Map<String, dynamic>)],
  );

  final ConversationSummary summary;
  final List<ChatMessage> messages;
}

class AiModel {
  const AiModel({
    required this.key,
    required this.provider,
    required this.model,
    required this.displayName,
    required this.capabilities,
    required this.costTier,
  });

  factory AiModel.fromJson(Map<String, dynamic> j) => AiModel(
    key: j['key'] as String,
    provider: j['provider'] as String,
    model: j['model'] as String,
    displayName: j['display_name'] as String,
    capabilities: [for (final c in j['capabilities'] as List<dynamic>) c as String],
    costTier: j['cost_tier'] as int,
  );

  final String key;
  final String provider;
  final String model;
  final String displayName;
  final List<String> capabilities;
  final int costTier;
}

/// One server-sent event from the chat streaming endpoints.
class ChatEvent {
  const ChatEvent(this.type, this.data);

  final String type; // meta | model | delta | done | error
  final Map<String, dynamic> data;
}
