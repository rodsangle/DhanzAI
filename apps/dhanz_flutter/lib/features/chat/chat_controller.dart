import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/platform/desktop.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';
import '../conversations/conversations_controller.dart';
import '../memory/memory_screen.dart';
import '../projects/projects_controller.dart';

/// Web research for the next messages: decided per message by the server, always, or never.
enum WebMode {
  auto,
  always,
  off;

  bool? get asRequest => switch (this) {
    WebMode.auto => null,
    WebMode.always => true,
    WebMode.off => false,
  };
}

class ChatState {
  const ChatState({
    this.conversationId,
    this.title,
    this.messages = const [],
    this.loading = false,
    this.streaming = false,
    this.error,
    this.modelKey,
    this.webMode = WebMode.auto,
    this.researchStatus,
    this.attachments = const [],
    this.uploading = 0,
    this.notice,
  });

  final String? conversationId;
  final String? title;
  final List<ChatMessage> messages;
  final bool loading;
  final bool streaming;
  final String? error;

  /// "provider:model" picked for this chat, or null for automatic routing.
  final String? modelKey;

  final WebMode webMode;

  /// What Dhanz is doing before the reply starts ("Searching the web…"), or null.
  final String? researchStatus;

  /// Files uploaded for the next message.
  final List<KnowledgeDocument> attachments;

  /// Uploads in progress.
  final int uploading;

  /// One-off information for the user (e.g. "Saved to memory"), shown once then cleared.
  final String? notice;

  ChatState copyWith({
    String? conversationId,
    String? title,
    List<ChatMessage>? messages,
    bool? loading,
    bool? streaming,
    String? Function()? error,
    String? Function()? modelKey,
    WebMode? webMode,
    String? Function()? researchStatus,
    List<KnowledgeDocument>? attachments,
    int? uploading,
    String? Function()? notice,
  }) => ChatState(
    conversationId: conversationId ?? this.conversationId,
    title: title ?? this.title,
    messages: messages ?? this.messages,
    loading: loading ?? this.loading,
    streaming: streaming ?? this.streaming,
    error: error != null ? error() : this.error,
    modelKey: modelKey != null ? modelKey() : this.modelKey,
    webMode: webMode ?? this.webMode,
    researchStatus: researchStatus != null ? researchStatus() : this.researchStatus,
    attachments: attachments ?? this.attachments,
    uploading: uploading ?? this.uploading,
    notice: notice != null ? notice() : this.notice,
  );
}

/// State of the open chat: loads history, sends messages and applies streamed deltas.
class ChatController extends Notifier<ChatState> {
  /// How often to check on a reply that is generating on the server without a live stream
  /// (after the app was backgrounded, the connection dropped, or a stop was requested).
  static Duration pollInterval = const Duration(seconds: 2);

  ChatStream? _active;
  StreamSubscription<ChatEvent>? _sub;
  Timer? _poll;
  int _loadToken = 0;

  ApiClient get _api => ref.read(apiClientProvider);

  @override
  ChatState build() {
    // A different account (or sign-out) starts from a blank chat.
    ref.watch(authControllerProvider.select((s) => s.value?.id));
    ref.onDispose(_stopLocal);
    return const ChatState();
  }

  /// Open a conversation (or a blank chat when [id] is null).
  Future<void> open(String? id) async {
    if (id != null && id == state.conversationId) return;
    _stopLocal();
    final token = ++_loadToken;
    if (id == null) {
      state = ChatState(modelKey: state.modelKey, webMode: state.webMode);
      return;
    }
    state = ChatState(conversationId: id, loading: true, modelKey: state.modelKey, webMode: state.webMode);
    try {
      final detail = await _api.conversation(id);
      if (token != _loadToken) return;
      state = state.copyWith(title: detail.summary.title, messages: detail.messages, loading: false);
      _followIfGenerating();
    } on ApiException catch (e) {
      if (token != _loadToken) return;
      state = state.copyWith(loading: false, error: () => e.message);
    }
  }

  /// Reloads the open conversation, e.g. when the app returns to the foreground or a push
  /// notification says a reply is ready.
  Future<void> refresh() async {
    if (_active != null) return; // the live stream is already up to date
    await _reload();
    _followIfGenerating();
  }

  bool get _generatingOnServer =>
      state.messages.isNotEmpty && !state.messages.last.isUser && state.messages.last.status == MessageStatus.streaming;

  /// The reply keeps generating on the server without a live stream: check on it until it ends.
  void _followIfGenerating() {
    _poll?.cancel();
    _poll = null;
    if (!_generatingOnServer) return;
    state = state.copyWith(streaming: true);
    final id = state.conversationId;
    _poll = Timer.periodic(pollInterval, (_) async {
      if (id != state.conversationId || _active != null) return;
      await _reload();
      if (!_generatingOnServer && id == state.conversationId) {
        _poll?.cancel();
        _poll = null;
        state = state.copyWith(streaming: false, researchStatus: () => null);
      }
    });
  }

  void selectModel(String? key) => state = state.copyWith(modelKey: () => key);

  void setWebMode(WebMode mode) => state = state.copyWith(webMode: mode);

  void clearNotice() => state = state.copyWith(notice: () => null);

  /// Uploads a file (into the selected project, if any) and attaches it to the next message.
  Future<void> attachFile(String filename, Uint8List bytes) async {
    state = state.copyWith(uploading: state.uploading + 1);
    try {
      final doc = await _api.uploadFile(filename, bytes, projectId: ref.read(selectedProjectProvider));
      state = state.copyWith(attachments: [...state.attachments, doc]);
    } on ApiException catch (e) {
      state = state.copyWith(error: () => '$filename: ${e.message}');
    } finally {
      state = state.copyWith(uploading: state.uploading - 1);
    }
  }

  void removeAttachment(String id) => state = state.copyWith(
    attachments: [
      for (final a in state.attachments)
        if (a.id != id) a,
    ],
  );

  void clearError() => state = state.copyWith(error: () => null);

  /// Sends [text]. Returns the conversation id (created on first send).
  Future<String?> send(String text) async {
    if (state.streaming || text.trim().isEmpty) return state.conversationId;
    var id = state.conversationId;
    final attachments = state.attachments;
    try {
      if (id == null) {
        final conv = await _api.createConversation(projectId: ref.read(selectedProjectProvider));
        id = conv.id;
        _loadToken++;
        state = state.copyWith(conversationId: id, title: conv.title);
      }
      final pendingUser = ChatMessage(
        id: 'pending-user',
        role: 'user',
        content: text,
        status: MessageStatus.complete,
        attachments: [for (final a in attachments) Attachment(id: a.id, filename: a.title, fileType: a.fileType)],
      );
      state = state.copyWith(messages: [...state.messages, pendingUser], error: () => null, attachments: const []);
      await _stream(
        () => _api.streamChat(
          id!,
          content: text,
          modelKey: state.modelKey,
          web: state.webMode.asRequest,
          attachmentIds: [for (final a in attachments) a.id],
        ),
      );
    } on ApiException catch (e) {
      state = state.copyWith(
        streaming: false,
        error: () => e.message,
        attachments: attachments, // keep the files so the user can retry
        messages: [
          for (final m in state.messages)
            if (!m.id.startsWith('pending')) m,
        ],
      );
    }
    unawaited(ref.read(conversationsProvider.notifier).refresh());
    return id;
  }

  /// Replaces user message [messageId] with [text] and regenerates from there.
  Future<void> editAndResend(String messageId, String text) async {
    final id = state.conversationId;
    if (id == null || state.streaming) return;
    final index = state.messages.indexWhere((m) => m.id == messageId);
    if (index < 0) return;
    final kept = state.messages.sublist(0, index);
    state = state.copyWith(
      messages: [
        ...kept,
        ChatMessage(id: 'pending-user', role: 'user', content: text, status: MessageStatus.complete),
      ],
      error: () => null,
    );
    try {
      await _stream(
        () => _api.streamChat(
          id,
          content: text,
          editMessageId: messageId,
          modelKey: state.modelKey,
          web: state.webMode.asRequest,
        ),
      );
    } on ApiException catch (e) {
      state = state.copyWith(streaming: false, error: () => e.message);
      await _reload();
    }
  }

  Future<void> regenerate() async {
    final id = state.conversationId;
    if (id == null || state.streaming) return;
    final lastUser = state.messages.lastIndexWhere((m) => m.isUser);
    if (lastUser < 0) return;
    state = state.copyWith(messages: state.messages.sublist(0, lastUser + 1), error: () => null);
    try {
      await _stream(
        () => _api.streamChat(id, regenerate: true, modelKey: state.modelKey, web: state.webMode.asRequest),
      );
    } on ApiException catch (e) {
      state = state.copyWith(streaming: false, error: () => e.message);
      await _reload();
    }
  }

  /// Stops generation. The server keeps the partial reply with status "stopped".
  Future<void> stop() async {
    final id = state.conversationId;
    _stopLocal();
    state = state.copyWith(
      streaming: false,
      researchStatus: () => null,
      messages: [
        for (final m in state.messages)
          m.status == MessageStatus.streaming ? m.copyWith(status: MessageStatus.stopped) : m,
      ],
    );
    if (id == null) return;
    try {
      await _api.stopReply(id);
    } on ApiException catch (e) {
      state = state.copyWith(error: () => 'Could not stop the reply: ${e.message}');
    }
    // Pick up the saved partial text (it can take the server a moment to wind down).
    if (id == state.conversationId) {
      await _reload();
      _followIfGenerating();
    }
  }

  /// Stops listening locally (the reply itself carries on generating on the server).
  void _stopLocal() {
    _poll?.cancel();
    _poll = null;
    unawaited(_sub?.cancel());
    _sub = null;
    _active?.cancel();
    _active = null;
  }

  Future<void> _reload() async {
    final id = state.conversationId;
    if (id == null) return;
    try {
      final detail = await _api.conversation(id);
      state = state.copyWith(title: detail.summary.title, messages: detail.messages);
    } on ApiException {
      // keep what we have
    }
  }

  Future<void> _stream(Future<ChatStream> Function() open) async {
    state = state.copyWith(streaming: true);
    final stream = await open();
    _active = stream;
    final done = Completer<void>();
    _sub = stream.events.listen(
      _apply,
      onError: (Object e) {
        // The reply keeps generating on the server; follow it by polling instead.
        _active?.cancel();
        _active = null;
        state = state.copyWith(notice: () => 'Connection lost. Dhanz is still writing; the answer will appear here.');
        _followIfGenerating();
        if (!_generatingOnServer) state = state.copyWith(streaming: false);
        if (!done.isCompleted) done.complete();
      },
      onDone: () {
        _active?.cancel();
        _active = null;
        if (state.streaming) {
          state = state.copyWith(streaming: false);
          _followIfGenerating(); // the stream ended without a final event
        }
        if (!done.isCompleted) done.complete();
      },
      cancelOnError: true,
    );
    await done.future;
  }

  void _apply(ChatEvent event) {
    final d = event.data;
    switch (event.type) {
      case 'meta':
        final user = d['user_message'];
        final assistant = ChatMessage(
          id: d['assistant_message_id'] as String,
          role: 'assistant',
          content: '',
          status: MessageStatus.streaming,
        );
        state = state.copyWith(
          messages: [
            for (final m in state.messages)
              if (m.id == 'pending-user' && user is Map<String, dynamic>) ChatMessage.fromJson(user) else m,
            assistant,
          ],
        );
      case 'research':
        switch (d['stage']) {
          case 'searching':
            state = state.copyWith(researchStatus: () => 'Searching the web for “${d['query']}”…');
          case 'reading':
            final n = (d['urls'] as List<dynamic>? ?? const []).length;
            state = state.copyWith(researchStatus: () => 'Reading $n ${n == 1 ? 'page' : 'pages'}…');
          case 'sources':
            final sources = Citation.listFrom(d['sources']);
            _updateLast((m) => m.copyWith(citations: sources));
            state = state.copyWith(researchStatus: () => 'Writing an answer from ${sources.length} sources…');
          case 'reading_files':
            state = state.copyWith(researchStatus: () => 'Reading your files…');
          case 'unavailable':
            state = state.copyWith(researchStatus: () => 'Web search isn’t available on this server.');
          default:
            break;
        }
      case 'memory':
        state = state.copyWith(notice: () => 'Saved to memory: “${d['content']}”');
        ref.invalidate(memoriesProvider);
      case 'model':
        _updateLast((m) => m.copyWith(provider: d['provider'] as String?, model: d['model'] as String?));
      case 'delta':
        if (state.researchStatus != null) state = state.copyWith(researchStatus: () => null);
        _updateLast((m) => m.copyWith(content: m.content + (d['text'] as String)));
      case 'done' || 'error' || 'stopped':
        state = state.copyWith(researchStatus: () => null);
        final msg = d['message'];
        if (msg is Map<String, dynamic>) {
          final finalMsg = ChatMessage.fromJson(msg);
          _updateLast((_) => finalMsg);
        }
        state = state.copyWith(
          streaming: false,
          error: () => event.type == 'error' ? (d['detail'] as String? ?? 'Something went wrong.') : null,
        );
        final id = state.conversationId;
        if (event.type == 'done' && id != null) {
          unawaited(
            ref
                .read(desktopShellProvider)
                .notifyReplyReady(conversationId: id, title: state.title ?? 'New conversation'),
          );
        }
    }
  }

  void _updateLast(ChatMessage Function(ChatMessage) update) {
    if (state.messages.isEmpty || state.messages.last.isUser) return;
    state = state.copyWith(
      messages: [...state.messages.sublist(0, state.messages.length - 1), update(state.messages.last)],
    );
  }
}

final chatControllerProvider = NotifierProvider<ChatController, ChatState>(ChatController.new);
