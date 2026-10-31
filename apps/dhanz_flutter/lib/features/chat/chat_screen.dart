import 'dart:async';

import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../models/models.dart';
import '../../widgets/dhanz_logo.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../conversations/conversation_panel.dart';
import '../conversations/conversations_controller.dart';
import 'chat_controller.dart';
import 'composer.dart';
import 'message_tile.dart';

const _wideBreakpoint = 900.0;

/// Main chat screen. On wide windows the conversation list is a permanent side panel;
/// on phones it is a drawer.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key, this.conversationId});

  final String? conversationId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  bool _dragging = false;

  /// Files dropped onto the chat (desktop) are attached to the next message.
  Future<void> _dropped(DropDoneDetails details) async {
    setState(() => _dragging = false);
    final chat = ref.read(chatControllerProvider.notifier);
    await Future.wait([for (final f in details.files) f.readAsBytes().then((b) => chat.attachFile(f.name, b))]);
  }

  @override
  void initState() {
    super.initState();
    _open();
  }

  @override
  void didUpdateWidget(covariant ChatScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversationId != widget.conversationId) _open();
  }

  void _open() {
    // Defer: providers must not be modified during build.
    Future.microtask(() => ref.read(chatControllerProvider.notifier).open(widget.conversationId));
  }

  /// Leaves the open conversation in history and shows a blank chat.
  ///
  /// `/chat` is the parent of `/chat/:id`. Going there shows the original blank
  /// screen again, but that screen does not reload, so the controller has to be
  /// cleared here or the previous messages stay on screen.
  void _newChat() {
    ref.read(chatControllerProvider.notifier).open(null);
    context.go('/chat');
  }

  Future<void> _send(String text) async {
    final id = await ref.read(chatControllerProvider.notifier).send(text);
    if (id != null && id != widget.conversationId && mounted) context.go('/chat/$id');
  }

  Future<void> _edit(ChatMessage message) async {
    final result = await showTextPrompt(
      context,
      title: 'Edit message',
      confirmLabel: 'Send',
      initialText: message.content,
      minLines: 3,
      maxLines: 8,
    );
    if (result != null && result.trim().isNotEmpty) {
      await ref.read(chatControllerProvider.notifier).editAndResend(message.id, result);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= _wideBreakpoint;
    final chat = ref.watch(chatControllerProvider);

    ref.listen(chatControllerProvider.select((s) => s.notice), (_, notice) {
      if (notice != null) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(notice)));
        ref.read(chatControllerProvider.notifier).clearNotice();
      }
    });
    ref.listen(chatControllerProvider.select((s) => s.error), (_, error) {
      if (error != null) {
        ScaffoldMessenger.of(context)
          ..hideCurrentSnackBar()
          ..showSnackBar(SnackBar(content: Text(error)));
        ref.read(chatControllerProvider.notifier).clearError();
      }
    });

    final column = Column(
      children: [
        if (chat.temporary)
          Material(
            color: Theme.of(context).colorScheme.secondaryContainer,
            child: ListTile(
              dense: true,
              leading: const Icon(Icons.timer_outlined),
              title: const Text('Temporary chat'),
              subtitle: const Text('Not saved to memory or your library, and deleted automatically after a day.'),
            ),
          ),
        Expanded(
          child: _MessageList(state: chat, onEdit: _edit, onSuggestion: _send),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 820),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Composer(key: ValueKey(chat.conversationId ?? 'new'), onSend: _send),
                  const SizedBox(height: 6),
                  Text(
                    'Dhanz can make mistakes. Verify important information.',
                    style: Theme.of(context).textTheme.labelSmall
                        ?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
    final body = DropTarget(
      enable: !chat.streaming,
      onDragEntered: (_) => setState(() => _dragging = true),
      onDragExited: (_) => setState(() => _dragging = false),
      onDragDone: (d) => unawaited(_dropped(d)),
      child: Stack(
        children: [
          column,
          if (_dragging)
            Positioned.fill(
              child: IgnorePointer(
                child: ColoredBox(
                  color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.85),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.file_upload_outlined, size: 48, color: Theme.of(context).colorScheme.secondary),
                        const SizedBox(height: 8),
                        const Text('Drop files to attach them'),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );

    // The list holds the server's latest title (auto-titled after the first message, or renamed).
    final listed = ref.watch(conversationsProvider).value?.where((c) => c.id == chat.conversationId).firstOrNull;
    final appBar = AppBar(
      automaticallyImplyLeading: !wide,
      title: Text(listed?.title ?? chat.title ?? AppConfig.appName, overflow: TextOverflow.ellipsis),
      actions: [
        if (chat.conversationId == null)
          IconButton(
            tooltip: chat.temporary ? 'Temporary chat on' : 'Temporary chat',
            isSelected: chat.temporary,
            icon: const Icon(Icons.timer_outlined),
            selectedIcon: const Icon(Icons.timer),
            onPressed: () => ref.read(chatControllerProvider.notifier).setTemporary(!chat.temporary),
          ),
        IconButton(tooltip: 'Talk to Dhanz', icon: const Icon(Icons.mic_none), onPressed: () => context.go('/voice')),
        IconButton(tooltip: 'New chat', icon: const Icon(Icons.edit_square), onPressed: _newChat),
      ],
    );

    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            const SizedBox(width: 300, child: ConversationPanel()),
            const VerticalDivider(width: 1),
            Expanded(
              child: Scaffold(appBar: appBar, body: body),
            ),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: appBar,
      drawer: const Drawer(width: 320, child: ConversationPanel(inDrawer: true)),
      body: body,
    );
  }
}

class _MessageList extends ConsumerWidget {
  const _MessageList({required this.state, required this.onEdit, required this.onSuggestion});

  final ChatState state;
  final ValueChanged<ChatMessage> onEdit;
  final ValueChanged<String> onSuggestion;

  static const _suggestions = [
    'Explain how solar panels convert light into electricity',
    'Write a Python function that removes duplicates from a list',
    'Help me plan a productive week',
    'Summarize the pros and cons of electric cars',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state.loading) return const Center(child: CircularProgressIndicator());
    final theme = Theme.of(context);
    if (state.messages.isEmpty) {
      return Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: Column(
              children: [
                const DhanzLogo(size: 76),
                const SizedBox(height: 20),
                Text(
                  AppConfig.greeting,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 28),
                Wrap(
                  alignment: WrapAlignment.center,
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    for (final s in _suggestions)
                      ActionChip(
                        label: Text(s),
                        onPressed: () => onSuggestion(s),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
    }

    final messages = state.messages;
    final lastAssistant = messages.lastIndexWhere((m) => !m.isUser);
    final controller = ref.read(chatControllerProvider.notifier);
    // reverse: true keeps the view pinned to the newest message while streaming.
    return ListView.builder(
      reverse: true,
      padding: const EdgeInsets.symmetric(vertical: 16),
      itemCount: messages.length,
      itemBuilder: (context, i) {
        final index = messages.length - 1 - i;
        final m = messages[index];
        return Center(
          key: ValueKey(m.id),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 820),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: MessageTile(
                message: m,
                isLast: index == lastAssistant && index == messages.length - 1,
                busy: state.streaming,
                onRegenerate: controller.regenerate,
                onEdit: onEdit,
                researchStatus: m.status == MessageStatus.streaming ? state.researchStatus : null,
              ),
            ),
          ),
        );
      },
    );
  }
}
