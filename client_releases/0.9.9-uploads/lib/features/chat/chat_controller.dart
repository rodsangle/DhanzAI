import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/platform/desktop.dart';
import '../../core/providers.dart';
import '../../core/uploads/upload_queue.dart';
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

class QueuedPrompt {
  const QueuedPrompt({required this.id, required this.text, required this.attachments, this.modelKey, this.web});
  final int id;
  final String text;
  final List<KnowledgeDocument> attachments;
  final String? modelKey;
  final bool? web;
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
    this.temporary = false,
    this.viewRevision = 0,
    this.queuedPrompts = const [],
    this.queuePaused = false,
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

  /// Temporary chat: not remembered, not added to the library, deleted after a day.
  final bool temporary;

  /// Changes when opening a chat so its message draft and scroll state start fresh.
  final int viewRevision;
  final List<QueuedPrompt> queuedPrompts;
  final bool queuePaused;

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
    bool? temporary,
    List<QueuedPrompt>? queuedPrompts,
    bool? queuePaused,
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
    temporary: temporary ?? this.temporary,
    viewRevision: viewRevision,
    queuedPrompts: queuedPrompts ?? this.queuedPrompts,
    queuePaused: queuePaused ?? this.queuePaused,
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
  int _nextUploadDraft = 0;
  String _blankUploadTarget = 'new:0';
  final _seenUploadErrors = <int>{};
  String get uploadTarget => state.conversationId == null ? _blankUploadTarget : 'conversation:${state.conversationId}';
  int _nextQueueId = 0;
  final _queues = <String?, List<QueuedPrompt>>{};
  final _pausedQueues = <String?>{};
  bool _openingReply = false;
  Completer<void>? _streamDone;
  int _streamGeneration = 0;

  ApiClient get _api => ref.read(apiClientProvider);

  @override
  ChatState build() {
    // A different account (or sign-out) starts from a blank chat.
    ref.watch(authControllerProvider.select((s) => s.value?.id));
    ref.watch(connectionRevisionProvider);
    _loadToken++;
    _blankUploadTarget = 'new:${++_nextUploadDraft}';
    _seenUploadErrors.clear();
    ref.listen(uploadQueueProvider, (_, entries) => _syncUploads(entries));
    _queues.clear();
    _pausedQueues.clear();
    ref.onDispose(_stopLocal);
    return const ChatState();
  }

  /// Open a conversation (or a blank chat when [id] is null).
  Future<void> open(String? id) async {
    if (id != null && id == state.conversationId) return;
    _queues[state.conversationId] = state.queuedPrompts;
    if (state.queuePaused) {
      _pausedQueues.add(state.conversationId);
    } else {
      _pausedQueues.remove(state.conversationId);
    }
    _stopLocal();
    final token = ++_loadToken;
    if (id == null) {
      _blankUploadTarget = 'new:${++_nextUploadDraft}';
      state = ChatState(
        modelKey: state.modelKey,
        webMode: state.webMode,
        viewRevision: state.viewRevision + 1,
        queuedPrompts: _queues[null] ?? const [],
        queuePaused: _pausedQueues.contains(null),
      );
      _syncUploads(ref.read(uploadQueueProvider));
      return;
    }
    state = ChatState(
      conversationId: id,
      loading: true,
      modelKey: state.modelKey,
      webMode: state.webMode,
      viewRevision: state.viewRevision + 1,
      queuedPrompts: _queues[id] ?? const [],
      queuePaused: _pausedQueues.contains(id),
    );
    _syncUploads(ref.read(uploadQueueProvider));
    try {
      final detail = await _api.conversation(id);
      if (token != _loadToken) return;
      state = state.copyWith(
        title: detail.summary.title,
        messages: detail.messages,
        loading: false,
        temporary: detail.summary.temporary,
      );
      _followIfGenerating();
      _drainQueue();
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
    if (_openingReply) return;
    if (!_generatingOnServer) {
      if (_active == null) {
        state = state.copyWith(streaming: false);
        _drainQueue();
      }
      return;
    }
    state = state.copyWith(streaming: true);
    final id = state.conversationId;
    final token = _loadToken;
    _poll = Timer.periodic(pollInterval, (_) async {
      if (id != state.conversationId || _active != null || token != _loadToken) return;
      await _reload();
      if (token != _loadToken) return;
      if (!_generatingOnServer && id == state.conversationId) {
        _poll?.cancel();
        _poll = null;
        state = state.copyWith(streaming: false, researchStatus: () => null);
        _drainQueue();
      }
    });
  }

  /// Only for a new chat: whether it is created as a temporary chat.
  void setTemporary(bool value) {
    if (state.conversationId == null) state = state.copyWith(temporary: value);
  }

  void selectModel(String? key) => state = state.copyWith(modelKey: () => key);

  void setWebMode(WebMode mode) => state = state.copyWith(webMode: mode);

  void clearNotice() => state = state.copyWith(notice: () => null);

  void _syncUploads(List<UploadEntry> entries) {
    final jobs = entries.where((job) => job.target == uploadTarget).toList();
    String? error;
    for (final job in jobs) {
      if (job.status == UploadStatus.failed && _seenUploadErrors.add(job.id)) {
        error = '${job.name}: ${job.error}. Check Uploads for details.';
      }
    }
    state = state.copyWith(
      uploading: jobs.where((job) => job.busy).length,
      attachments: [for (final job in jobs) if (job.attachable && job.document != null) job.document!],
      error: error == null ? null : () => error,
    );
  }

  /// The app queue owns the request; changing routes/chats cannot interrupt it.
  Future<void> attachFile(String filename, Uint8List bytes) async {
    final queue = ref.read(uploadQueueProvider.notifier);
    final ids = queue.files([(name: filename, bytes: bytes)], ticket: queue.ticket(),
      projectId: ref.read(selectedProjectProvider), target: uploadTarget);
    if (ids.isNotEmpty) await queue.waitFor(ids.single);
  }

  void removeAttachment(String id) {
    ref.read(uploadQueueProvider.notifier).consume(uploadTarget, [id]);
  }

  void clearError() => state = state.copyWith(error: () => null);

  /// Sends [text]. Returns the conversation id (created on first send).
  Future<String?> send(String text, {bool? webOverride}) async {
    if (text.trim().isEmpty || state.uploading > 0) return state.conversationId;
    final prompt = QueuedPrompt(
      id: _nextQueueId++,
      text: text,
      attachments: List.of(state.attachments),
      modelKey: state.modelKey,
      web: webOverride ?? state.webMode.asRequest,
    );
    ref.read(uploadQueueProvider.notifier).consume(uploadTarget, prompt.attachments.map((d) => d.id));
    state = state.copyWith(attachments: const []);
    if (state.streaming || _openingReply || _active != null || state.queuedPrompts.isNotEmpty) {
      state = state.copyWith(queuedPrompts: [...state.queuedPrompts, prompt]);
      _drainQueue();
      return state.conversationId;
    }
    state = state.copyWith(queuePaused: false);
    return _sendPrompt(prompt);
  }

  void removeQueuedPrompt(int id) =>
      state = state.copyWith(queuedPrompts: state.queuedPrompts.where((prompt) => prompt.id != id).toList());

  void resumeQueue() {
    state = state.copyWith(queuePaused: false);
    _drainQueue();
  }

  void _drainQueue() {
    if (state.streaming ||
        state.loading ||
        _openingReply ||
        _active != null ||
        state.queuePaused ||
        state.queuedPrompts.isEmpty) {
      return;
    }
    final prompt = state.queuedPrompts.first;
    state = state.copyWith(queuedPrompts: state.queuedPrompts.sublist(1));
    unawaited(_sendPrompt(prompt));
  }

  void _scheduleQueueDrain() {
    final token = _loadToken;
    Timer.run(() {
      if (token == _loadToken) _drainQueue();
    });
  }

  Future<String?> _sendPrompt(QueuedPrompt prompt) async {
    var id = state.conversationId;
    final token = ++_loadToken;
    final text = prompt.text;
    final attachments = prompt.attachments;
    _openingReply = true;
    state = state.copyWith(streaming: true);
    try {
      if (id == null) {
        final conv = await _api.createConversation(
          projectId: ref.read(selectedProjectProvider),
          temporary: state.temporary,
        );
        id = conv.id;
        if (token != _loadToken) return id;
        final oldUploadTarget = uploadTarget;
        state = state.copyWith(conversationId: id, title: conv.title);
        ref.read(uploadQueueProvider.notifier).retarget(oldUploadTarget, uploadTarget);
        _syncUploads(ref.read(uploadQueueProvider));
      }
      final pendingUser = ChatMessage(
        id: 'pending-user',
        role: 'user',
        content: text,
        status: MessageStatus.complete,
        attachments: [for (final a in attachments) Attachment(id: a.id, filename: a.title, fileType: a.fileType)],
      );
      state = state.copyWith(messages: [...state.messages, pendingUser], error: () => null);
      await _stream(
        () => _api.streamChat(
          id!,
          content: text,
          modelKey: prompt.modelKey,
          web: prompt.web,
          attachmentIds: [for (final a in attachments) a.id],
        ),
      );
    } on ApiException catch (e) {
      if (token != _loadToken) return id;
      _openingReply = false;
      state = state.copyWith(
        streaming: false,
        error: () => e.message,
        queuedPrompts: [prompt, ...state.queuedPrompts],
        queuePaused: true,
        messages: [
          for (final m in state.messages)
            if (!m.id.startsWith('pending')) m,
        ],
      );
    }
    if (token == _loadToken) {
      unawaited(ref.read(conversationsProvider.notifier).refresh());
      _scheduleQueueDrain();
    }
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
      queuePaused: state.queuedPrompts.isNotEmpty,
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
    _loadToken++;
    _streamGeneration++;
    _openingReply = false;
    if (_streamDone?.isCompleted == false) _streamDone!.complete();
    _streamDone = null;
    _poll?.cancel();
    _poll = null;
    unawaited(_sub?.cancel());
    _sub = null;
    _active?.cancel();
    _active = null;
  }

  Future<void> _reload() async {
    final token = _loadToken;
    final id = state.conversationId;
    if (id == null) return;
    try {
      final detail = await _api.conversation(id);
      if (id != state.conversationId || token != _loadToken) return;
      state = state.copyWith(title: detail.summary.title, messages: detail.messages);
    } on ApiException {
      // keep what we have
    }
  }

  Future<void> _stream(Future<ChatStream> Function() open) async {
    final generation = _streamGeneration;
    _openingReply = true;
    state = state.copyWith(streaming: true);
    late final ChatStream stream;
    try {
      stream = await open();
    } catch (_) {
      if (generation == _streamGeneration) {
        _openingReply = false;
        state = state.copyWith(queuePaused: state.queuedPrompts.isNotEmpty);
      }
      rethrow;
    }
    if (generation != _streamGeneration) {
      stream.cancel();
      return;
    }
    _openingReply = false;
    _active = stream;
    final done = Completer<void>();
    _streamDone = done;
    _sub = stream.events.listen(
      (event) {
        if (generation == _streamGeneration) _apply(event);
      },
      onError: (Object e) {
        if (generation != _streamGeneration) return;
        // The reply keeps generating on the server; follow it by polling instead.
        _active?.cancel();
        _active = null;
        state = state.copyWith(notice: () => 'Connection lost. Dhanz is still writing; the answer will appear here.');
        _followIfGenerating();
        if (!_generatingOnServer) state = state.copyWith(streaming: false);
        if (!done.isCompleted) done.complete();
      },
      onDone: () {
        if (generation != _streamGeneration) return;
        _active?.cancel();
        _active = null;
        if (state.streaming) {
          state = state.copyWith(streaming: false);
          _followIfGenerating(); // the stream ended without a final event
        }
        if (!done.isCompleted) done.complete();
        _scheduleQueueDrain();
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
      case 'tool':
        if (d['stage'] == 'running') {
          final labels = (d['labels'] as List<dynamic>? ?? const []).cast<String>();
          state = state.copyWith(researchStatus: () => labels.isEmpty ? 'Working…' : '${labels.join(', ')}…');
        } else {
          final added = ToolActivity.listFrom(d['activity']);
          _updateLast((m) => m.copyWith(toolActivity: [...m.toolActivity, ...added]));
          state = state.copyWith(researchStatus: () => null);
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
          queuePaused: event.type != 'done' && state.queuedPrompts.isNotEmpty ? true : state.queuePaused,
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
