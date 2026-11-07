import 'dart:async';

import 'package:desktop_drop/desktop_drop.dart';
import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:window_manager/window_manager.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../core/uploads/upload_queue.dart';
import '../projects/projects_controller.dart';
import '../auth/auth_controller.dart';
import '../../models/models.dart';
import '../../widgets/dhanz_logo.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../conversations/conversation_panel.dart';
import '../conversations/conversations_controller.dart';
import '../automation/automation_screen.dart';
import 'chat_controller.dart';
import 'chat_suggestions.dart';
import 'composer.dart';
import 'daily_news_button.dart';
import 'message_tile.dart';
import 'attachment_chip.dart';
import 'chat_preview.dart';
import '../builder/app_simulator.dart';

const _wideBreakpoint = 900.0;

/// Main chat screen. On wide windows the conversation list is a permanent side panel;
/// on phones it is a drawer.
class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key, this.conversationId});

  final String? conversationId;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> with WindowListener {
  final _preview = ChatPreviewController();
  int? _previewRevision;
  bool _dragging = false;
  bool _discretion = false;
  bool _savingDiscretion = false;
  List<String> _suggestions = randomChatSuggestions();
  bool get _windows =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.windows;

  /// Files dropped onto the chat (desktop) are attached to the next message.
  Future<void> _dropped(DropDoneDetails details) async {
    setState(() => _dragging = false);
    final queue = ref.read(uploadQueueProvider.notifier);
    final ticket = queue.ticket();
    final target = ref.read(chatControllerProvider.notifier).uploadTarget;
    final project = ref.read(selectedProjectProvider);
    try {
      final files = await Future.wait(
        details.files.map(
          (file) async => (name: file.name, bytes: await file.readAsBytes()),
        ),
      );
      queue.files(files, ticket: ticket, projectId: project, target: target);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    }
  }

  @override
  void initState() {
    super.initState();
    if (_windows) windowManager.addListener(this);
    _open();
    unawaited(_loadDiscretion());
  }

  Future<void> _loadDiscretion() async {
    try {
      final enabled = await ref.read(apiClientProvider).autonomyEnabled();
      if (mounted) setState(() => _discretion = enabled);
    } catch (_) {}
  }

  Future<void> _toggleDiscretion() async {
    if (_savingDiscretion) return;
    setState(() => _savingDiscretion = true);
    try {
      await ref.read(apiClientProvider).setAutonomy(!_discretion);
      if (!mounted) return;
      setState(() => _discretion = !_discretion);
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(_discretion ?
        'Use discretion is on for chat and Codex. Existing permissions still apply.' : 'Use discretion is off.')));
    } on ApiException catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) setState(() => _savingDiscretion = false);
    }
  }

  @override
  void onWindowFocus() {
    if (mounted) setState(() => _suggestions = randomChatSuggestions());
  }

  @override
  void dispose() {
    _preview.dispose();
    if (_windows) windowManager.removeListener(this);
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant ChatScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversationId != widget.conversationId) _open();
  }

  void _open() {
    // Defer: providers must not be modified during build.
    Future.microtask(
      () =>
          ref.read(chatControllerProvider.notifier).open(widget.conversationId),
    );
  }

  Future<void> _send(String text, {bool? webOverride}) async {
    final id = await ref
        .read(chatControllerProvider.notifier)
        .send(text, webOverride: webOverride);
    if (id != null && id != widget.conversationId && mounted) {
      context.go('/chat/$id');
    }
  }

  void _continueInCodex(String text) {
    final chat = ref.read(chatControllerProvider);
    context.go(
      '/coding',
      extra: <String, dynamic>{
        'task': text,
        'conversation_id': chat.temporary ? null : chat.conversationId,
        'user_id': ref.read(authControllerProvider).value?.id,
        'server': ref.read(apiClientProvider).baseUrl,
        'temporary': chat.temporary,
        'has_attachments': chat.attachments.isNotEmpty,
      },
    );
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
      await ref
          .read(chatControllerProvider.notifier)
          .editAndResend(message.id, result);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= _wideBreakpoint;
    final chat = ref.watch(chatControllerProvider);
    if (_previewRevision != chat.viewRevision) {
      _previewRevision = chat.viewRevision;
      _preview.clear(notify: false);
    }

    ref.listen(chatControllerProvider.select((state) => state.conversationId), (
      _,
      id,
    ) {
      if (id != null && id != widget.conversationId && mounted) {
        context.go('/chat/$id');
      }
    });

    ref.listen(chatControllerProvider.select((s) => s.notice), (_, notice) {
      if (notice != null) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(notice)));
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
              subtitle: const Text(
                'Not saved to memory or your library, and deleted automatically after a day.',
              ),
            ),
          ),
        Expanded(
          child: _MessageList(
            key: ValueKey(chat.viewRevision),
            state: chat,
            onEdit: _edit,
            onSuggestion: _send,
            suggestions: _suggestions,
          ),
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
                  DailyNewsButton(
                    enabled: !chat.loading,
                    onSend: (text) => _send(text, webOverride: true),
                  ),
                  Composer(
                    key: ValueKey(chat.viewRevision),
                    onSend: _send,
                    onCodex: _continueInCodex,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Dhanz can make mistakes. Verify important information.',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ],
    );
    final body = DropTarget(
      enable: !chat.loading,
      onDragEntered: (_) => setState(() => _dragging = true),
      onDragExited: (_) => setState(() => _dragging = false),
      onDragDone: (d) => unawaited(_dropped(d)),
      child: Stack(
        children: [
          column,
          const Positioned.fill(child: ChatApprovalPanel()),
          if (_dragging)
            Positioned.fill(
              child: IgnorePointer(
                child: ColoredBox(
                  color: Theme.of(context).colorScheme.surface
                      .withValues(alpha: 0.85),
                  child: Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.file_upload_outlined,
                          size: 48,
                          color: Theme.of(context).colorScheme.secondary,
                        ),
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
    final listed = ref
        .watch(conversationsProvider)
        .value
        ?.where((c) => c.id == chat.conversationId)
        .firstOrNull;
    final appBar = AppBar(
      automaticallyImplyLeading: !wide,
      title: Text(
        listed?.title ?? chat.title ?? AppConfig.appName,
        overflow: TextOverflow.ellipsis,
      ),
      actions: [
        if (!wide) PopupMenuButton<String>(tooltip: 'Chat options',
          onSelected: (value) {
            if (value == 'discretion') unawaited(_toggleDiscretion());
            if (value == 'temporary') ref.read(chatControllerProvider.notifier).setTemporary(!chat.temporary);
            if (value == 'voice') context.go('/voice');
          },
          itemBuilder: (_) => [
            CheckedPopupMenuItem(value: 'discretion', checked: _discretion, enabled: !_savingDiscretion, child: const Text('Use discretion')),
            if (chat.conversationId == null) CheckedPopupMenuItem(value: 'temporary', checked: chat.temporary, child: const Text('Temporary chat')),
            const PopupMenuItem(value: 'voice', child: Text('Talk to Dhanz')),
          ]),
        if (wide) IconButton(tooltip: _discretion ? 'Use discretion: on' : 'Use discretion: off',
          isSelected: _discretion, icon: const Icon(Icons.auto_awesome), onPressed: _savingDiscretion ? null : _toggleDiscretion),
        IconButton(tooltip: 'App simulator', icon: const Icon(Icons.smartphone_outlined),
          onPressed: () => _preview.open(const ChatPreviewTarget(documentId: 'app-simulator',
            filename: 'App simulator', simulator: true))),
        AnimatedBuilder(
          animation: _preview,
          builder: (context, _) => IconButton(
            tooltip: _preview.visible ? 'Close preview' : 'Preview',
            icon: const Icon(Icons.vertical_split_outlined),
            isSelected: _preview.visible,
            onPressed: _preview.visible ? _preview.close : _preview.show,
          ),
        ),
        if (wide && chat.conversationId == null)
          IconButton(
            tooltip: chat.temporary ? 'Temporary chat on' : 'Temporary chat',
            isSelected: chat.temporary,
            icon: const Icon(Icons.timer_outlined),
            selectedIcon: const Icon(Icons.timer),
            onPressed: () => ref
                .read(chatControllerProvider.notifier)
                .setTemporary(!chat.temporary),
          ),
        if (wide) IconButton(
          tooltip: 'Talk to Dhanz',
          icon: const Icon(Icons.mic_none),
          onPressed: () => context.go('/voice'),
        ),
        IconButton(
          tooltip: 'New chat',
          icon: const Icon(Icons.edit_square),
          onPressed: () {
            _preview.clear();
            ref.read(chatControllerProvider.notifier).open(null);
            context.go('/chat');
          },
        ),
      ],
    );

    final previewBody = ChatPreviewHost(
      controller: _preview,
      previewBuilder: (context, target) => target.simulator ? AppSimulatorPanel(
        initialProjectId: target.projectId,
        listProjects: ref.read(apiClientProvider).builderProjects,
        loadProject: ref.read(apiClientProvider).builderProject,
        reviseProject: ref.read(apiClientProvider).reviseBuilderProject,
        downloadProject: ref.read(apiClientProvider).downloadBuilderProject,
      ) : FilePreviewContent(
        documentId: target.documentId,
        filename: target.filename,
        embedded: true,
      ),
      child: body,
    );
    if (wide) {
      return Scaffold(
        body: Row(
          children: [
            const SizedBox(width: 300, child: ConversationPanel()),
            const VerticalDivider(width: 1),
            Expanded(
              child: Scaffold(appBar: appBar, body: previewBody),
            ),
          ],
        ),
      );
    }
    return Scaffold(
      appBar: appBar,
      drawer: const Drawer(
        width: 320,
        child: ConversationPanel(inDrawer: true),
      ),
      body: previewBody,
    );
  }
}

class _MessageList extends ConsumerWidget {
  const _MessageList({
    super.key,
    required this.state,
    required this.onEdit,
    required this.onSuggestion,
    required this.suggestions,
  });

  final ChatState state;
  final ValueChanged<ChatMessage> onEdit;
  final ValueChanged<String> onSuggestion;

  final List<String> suggestions;

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
                  style: theme.textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 28),
                Wrap(
                  alignment: WrapAlignment.center,
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    for (final s in suggestions)
                      ActionChip(
                        label: Text(s),
                        onPressed: () => onSuggestion(s),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
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
                researchStatus: m.status == MessageStatus.streaming
                    ? state.researchStatus
                    : null,
              ),
            ),
          ),
        );
      },
    );
  }
}
