import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../auth/auth_controller.dart';
import '../conversations/conversations_controller.dart';

class ChatState {
  const ChatState({
    this.conversationId,
    this.title,
    this.messages = const [],
    this.loading = false,
    this.streaming = false,
    this.error,
    this.modelKey,
  });

  final String? conversationId;
  final String? title;
  final List<ChatMessage> messages;
  final bool loading;
  final bool streaming;
  final String? error;

  /// "provider:model" picked for this chat, or null for automatic routing.
  final String? modelKey;

  ChatState copyWith({
    String? conversationId,
    String? title,
    List<ChatMessage>? messages,
    bool? loading,
    bool? streaming,
    String? Function()? error,
    String? Function()? modelKey,
  }) => ChatState(
    conversationId: conversationId ?? this.conversationId,
    title: title ?? this.title,
    messages: messages ?? this.messages,
    loading: loading ?? this.loading,
    streaming: streaming ?? this.streaming,
    error: error != null ? error() : this.error,
    modelKey: modelKey != null ? modelKey() : this.modelKey,
  );
}

/// State of the open chat: loads history, sends messages and applies streamed deltas.
class ChatController extends Notifier<ChatState> {
  ChatStream? _active;
  StreamSubscription<ChatEvent>? _sub;
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
      state = ChatState(modelKey: state.modelKey);
      return;
    }
    state = ChatState(conversationId: id, loading: true, modelKey: state.modelKey);
    try {
      final detail = await _api.conversation(id);
      if (token != _loadToken) return;
      state = state.copyWith(title: detail.summary.title, messages: detail.messages, loading: false);
    } on ApiException catch (e) {
      if (token != _loadToken) return;
      state = state.copyWith(loading: false, error: () => e.message);
    }
  }

  void selectModel(String? key) => state = state.copyWith(modelKey: () => key);

  void clearError() => state = state.copyWith(error: () => null);

  /// Sends [text]. Returns the conversation id (created on first send).
  Future<String?> send(String text) async {
    if (state.streaming || text.trim().isEmpty) return state.conversationId;
    var id = state.conversationId;
    try {
      if (id == null) {
        final conv = await _api.createConversation();
        id = conv.id;
        _loadToken++;
        state = state.copyWith(conversationId: id, title: conv.title);
      }
      final pendingUser = ChatMessage(id: 'pending-user', role: 'user', content: text, status: MessageStatus.complete);
      state = state.copyWith(messages: [...state.messages, pendingUser], error: () => null);
      await _stream(() => _api.streamChat(id!, content: text, modelKey: state.modelKey));
    } on ApiException catch (e) {
      state = state.copyWith(
        streaming: false,
        error: () => e.message,
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
      await _stream(() => _api.streamChat(id, content: text, editMessageId: messageId, modelKey: state.modelKey));
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
      await _stream(() => _api.streamChat(id, regenerate: true, modelKey: state.modelKey));
    } on ApiException catch (e) {
      state = state.copyWith(streaming: false, error: () => e.message);
      await _reload();
    }
  }

  /// Stops generation. The server keeps the partial reply with status "stopped".
  void stop() {
    _stopLocal();
    state = state.copyWith(
      streaming: false,
      messages: [
        for (final m in state.messages)
          m.status == MessageStatus.streaming ? m.copyWith(status: MessageStatus.stopped) : m,
      ],
    );
  }

  void _stopLocal() {
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
        state = state.copyWith(streaming: false, error: () => 'Connection lost while streaming the reply.');
        if (!done.isCompleted) done.complete();
      },
      onDone: () {
        _active?.cancel();
        _active = null;
        if (state.streaming) state = state.copyWith(streaming: false);
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
      case 'model':
        _updateLast((m) => m.copyWith(provider: d['provider'] as String?, model: d['model'] as String?));
      case 'delta':
        _updateLast((m) => m.copyWith(content: m.content + (d['text'] as String)));
      case 'done' || 'error':
        final msg = d['message'];
        if (msg is Map<String, dynamic>) {
          final finalMsg = ChatMessage.fromJson(msg);
          _updateLast((_) => finalMsg);
        }
        state = state.copyWith(
          streaming: false,
          error: () => event.type == 'error' ? (d['detail'] as String? ?? 'Something went wrong.') : null,
        );
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
