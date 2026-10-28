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
    this.autoIndexWeb = true,
    this.memoryEnabled = false,
  });

  factory User.fromJson(Map<String, dynamic> j) => User(
    id: j['id'] as String,
    email: j['email'] as String,
    displayName: j['display_name'] as String,
    role: j['role'] as String,
    routingPolicy: j['routing_policy'] as String,
    preferredModel: j['preferred_model'] as String?,
    autoIndexWeb: j['auto_index_web'] as bool? ?? true,
    memoryEnabled: j['memory_enabled'] as bool? ?? false,
  );

  final String id;
  final String email;
  final String displayName;
  final String role;
  final String routingPolicy;
  final String? preferredModel;

  /// Save pages read during web research to the knowledge library.
  final bool autoIndexWeb;

  /// Opt-in long-term memory.
  final bool memoryEnabled;
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
  const ConversationSummary({
    required this.id,
    required this.title,
    required this.pinned,
    required this.updatedAt,
    this.projectId,
  });

  factory ConversationSummary.fromJson(Map<String, dynamic> j) => ConversationSummary(
    id: j['id'] as String,
    title: j['title'] as String,
    pinned: j['pinned'] as bool,
    updatedAt: _date(j['updated_at']),
    projectId: j['project_id'] as String?,
  );

  final String id;
  final String title;
  final bool pinned;
  final DateTime updatedAt;
  final String? projectId;
}

/// A file attached to a user message.
class Attachment {
  const Attachment({required this.id, required this.filename, this.fileType, this.mimeType});

  factory Attachment.fromJson(Map<String, dynamic> j) => Attachment(
    id: j['id'] as String,
    filename: j['filename'] as String,
    fileType: j['file_type'] as String?,
    mimeType: j['mime_type'] as String?,
  );

  static List<Attachment> listFrom(Object? raw) =>
      raw is List ? [for (final a in raw) Attachment.fromJson(a as Map<String, dynamic>)] : const [];

  final String id;
  final String filename;
  final String? fileType;
  final String? mimeType;

  bool get isImage => fileType == 'image';
}

class Project {
  const Project({required this.id, required this.name, this.description, this.instructions});

  factory Project.fromJson(Map<String, dynamic> j) => Project(
    id: j['id'] as String,
    name: j['name'] as String,
    description: j['description'] as String?,
    instructions: j['instructions'] as String?,
  );

  final String id;
  final String name;
  final String? description;
  final String? instructions;
}

class Memory {
  const Memory({required this.id, required this.content, required this.source, required this.createdAt});

  factory Memory.fromJson(Map<String, dynamic> j) => Memory(
    id: j['id'] as String,
    content: j['content'] as String,
    source: j['source'] as String,
    createdAt: _date(j['created_at']),
  );

  final String id;
  final String content;
  final String source; // manual | chat
  final DateTime createdAt;
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
    this.citations = const [],
    this.attachments = const [],
  });

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
    id: j['id'] as String,
    role: j['role'] as String,
    content: j['content'] as String,
    status: MessageStatus.values.asNameMap()[j['status']] ?? MessageStatus.complete,
    provider: j['provider'] as String?,
    model: j['model'] as String?,
    error: j['error'] as String?,
    citations: Citation.listFrom(j['citations']),
    attachments: Attachment.listFrom(j['attachments']),
  );

  final String id;
  final String role;
  final String content;
  final MessageStatus status;
  final String? provider;
  final String? model;
  final String? error;

  /// Numbered sources the reply cites as [n].
  final List<Citation> citations;

  /// Files attached to a user message.
  final List<Attachment> attachments;

  bool get isUser => role == 'user';

  ChatMessage copyWith({
    String? content,
    MessageStatus? status,
    String? provider,
    String? model,
    String? error,
    List<Citation>? citations,
  }) => ChatMessage(
    id: id,
    role: role,
    content: content ?? this.content,
    status: status ?? this.status,
    provider: provider ?? this.provider,
    model: model ?? this.model,
    error: error ?? this.error,
    citations: citations ?? this.citations,
    attachments: attachments,
  );
}

class Citation {
  const Citation({
    required this.n,
    required this.title,
    required this.url,
    this.siteName,
    this.publishedAt,
    this.retrievedAt,
    this.origin = 'web',
  });

  factory Citation.fromJson(Map<String, dynamic> j) => Citation(
    n: j['n'] as int,
    title: j['title'] as String,
    url: j['url'] as String,
    siteName: j['site_name'] as String?,
    publishedAt: _maybeDate(j['published_at']),
    retrievedAt: _maybeDate(j['retrieved_at']),
    origin: j['origin'] as String? ?? 'web',
  );

  static List<Citation> listFrom(Object? raw) =>
      raw is List ? [for (final c in raw) Citation.fromJson(c as Map<String, dynamic>)] : const [];

  final int n;
  final String title;
  final String url;
  final String? siteName;
  final DateTime? publishedAt;
  final DateTime? retrievedAt;
  final String origin; // web | library

  bool get fromLibrary => origin == 'library';

  bool get fromFile => origin == 'file';

  /// Library document id for uploaded files (`upload:<id>` URLs).
  String? get uploadId => url.startsWith('upload:') ? url.substring('upload:'.length) : null;

  String get host => Uri.tryParse(url)?.host.replaceFirst('www.', '') ?? url;
}

DateTime? _maybeDate(Object? v) => v is String ? DateTime.tryParse(v)?.toLocal() : null;

/// Optional server features (Phase 2).
class Features {
  const Features({
    this.webSearch = false,
    this.semanticSearch = false,
    this.speechToText = false,
    this.malwareScanning = false,
    this.vision = false,
    this.maxUploadMb = 20,
  });

  factory Features.fromJson(Map<String, dynamic>? j) => Features(
    webSearch: j?['web_search'] as bool? ?? false,
    semanticSearch: j?['semantic_search'] as bool? ?? false,
    speechToText: j?['speech_to_text'] as bool? ?? false,
    malwareScanning: j?['malware_scanning'] as bool? ?? false,
    vision: j?['vision'] as bool? ?? false,
    maxUploadMb: j?['max_upload_mb'] as int? ?? 20,
  );

  final bool webSearch;
  final bool semanticSearch;
  final bool speechToText;
  final bool malwareScanning;
  final bool vision;
  final int maxUploadMb;
}

class KnowledgeDocument {
  const KnowledgeDocument({
    required this.id,
    required this.url,
    required this.title,
    required this.retrievedAt,
    required this.addedVia,
    this.siteName,
    this.publishedAt,
    this.content,
    this.kind = 'web',
    this.projectId,
    this.fileType,
    this.sizeBytes,
    this.scanStatus,
    this.notes,
  });

  factory KnowledgeDocument.fromJson(Map<String, dynamic> j) => KnowledgeDocument(
    id: j['id'] as String,
    url: j['url'] as String,
    title: j['title'] as String,
    siteName: j['site_name'] as String?,
    publishedAt: _maybeDate(j['published_at']),
    retrievedAt: _date(j['retrieved_at']),
    addedVia: j['added_via'] as String,
    content: j['content'] as String?,
    kind: j['kind'] as String? ?? 'web',
    projectId: j['project_id'] as String?,
    fileType: j['file_type'] as String?,
    sizeBytes: j['size_bytes'] as int?,
    scanStatus: j['scan_status'] as String?,
    notes: j['notes'] as String?,
  );

  final String id;
  final String url;
  final String title;
  final String? siteName;
  final DateTime? publishedAt;
  final DateTime retrievedAt;
  final String addedVia; // manual | research | upload
  final String? content;
  final String kind; // web | file
  final String? projectId;
  final String? fileType;
  final int? sizeBytes;
  final String? scanStatus;
  final String? notes;

  bool get isFile => kind == 'file';

  String get host => Uri.tryParse(url)?.host.replaceFirst('www.', '') ?? url;
}

class LibraryHit {
  const LibraryHit({required this.documentId, required this.title, required this.url, required this.snippet});

  factory LibraryHit.fromJson(Map<String, dynamic> j) => LibraryHit(
    documentId: j['document_id'] as String,
    title: j['title'] as String,
    url: j['url'] as String,
    snippet: j['snippet'] as String,
  );

  final String documentId;
  final String title;
  final String url;
  final String snippet;
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
