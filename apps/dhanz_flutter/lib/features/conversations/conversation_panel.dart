import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/dhanz_logo.dart';
import '../auth/auth_controller.dart';
import '../chat/chat_controller.dart';
import 'conversations_controller.dart';

/// Conversation history: search, open, rename, pin, export and delete.
class ConversationPanel extends ConsumerStatefulWidget {
  const ConversationPanel({super.key, this.inDrawer = false});

  final bool inDrawer;

  @override
  ConsumerState<ConversationPanel> createState() => _ConversationPanelState();
}

class _ConversationPanelState extends ConsumerState<ConversationPanel> {
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    super.dispose();
  }

  void _go(String location) {
    final router = GoRouter.of(context);
    if (widget.inDrawer) Navigator.of(context).pop();
    router.go(location);
  }

  Future<void> _run(Future<void> Function() action) async {
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _rename(ConversationSummary c) async {
    final controller = TextEditingController(text: c.title);
    final title = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename conversation'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLength: 200,
          onSubmitted: (v) => Navigator.pop(context, v),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, controller.text), child: const Text('Save')),
        ],
      ),
    );
    controller.dispose();
    if (title != null && title.trim().isNotEmpty) {
      await _run(() => ref.read(conversationsProvider.notifier).rename(c.id, title.trim()));
    }
  }

  Future<void> _delete(ConversationSummary c) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete conversation?'),
        content: Text('"${c.title}" will be permanently deleted.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Theme.of(context).colorScheme.error),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await _run(() => ref.read(conversationsProvider.notifier).delete(c.id));
    if (ref.read(chatControllerProvider).conversationId == c.id && mounted) _go('/chat');
  }

  Future<void> _export(ConversationSummary c, String format) async {
    await _run(() async {
      final text = await ref.read(apiClientProvider).exportConversation(c.id, format: format);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Export · ${format == 'markdown' ? 'Markdown' : 'Text'}'),
          content: SizedBox(
            width: 600,
            height: 420,
            child: SingleChildScrollView(
              child: SelectableText(text, style: const TextStyle(fontFamily: 'monospace')),
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
            FilledButton.icon(
              icon: const Icon(Icons.copy_rounded),
              label: const Text('Copy'),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: text));
                if (context.mounted) Navigator.pop(context);
              },
            ),
          ],
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final conversations = ref.watch(conversationsProvider);
    final currentId = ref.watch(chatControllerProvider.select((s) => s.conversationId));
    final user = ref.watch(authControllerProvider).value;

    return Material(
      color: theme.colorScheme.surfaceContainerLow,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Row(
                children: [
                  const DhanzLogo(size: 34),
                  const SizedBox(width: 10),
                  Text(
                    'DHANZ AI',
                    style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800, letterSpacing: 1.5),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              child: FilledButton.icon(
                onPressed: () => _go('/chat'),
                icon: const Icon(Icons.add),
                label: const Text('New chat'),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
              child: TextField(
                decoration: const InputDecoration(
                  hintText: 'Search conversations',
                  prefixIcon: Icon(Icons.search),
                  isDense: true,
                ),
                onChanged: (q) {
                  _debounce?.cancel();
                  _debounce = Timer(
                    const Duration(milliseconds: 350),
                    () => ref.read(conversationSearchProvider.notifier).set(q.trim()),
                  );
                },
              ),
            ),
            Expanded(
              child: conversations.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => Center(
                  child: TextButton.icon(
                    onPressed: () => ref.invalidate(conversationsProvider),
                    icon: const Icon(Icons.refresh),
                    label: const Text('Could not load. Retry'),
                  ),
                ),
                data: (items) => items.isEmpty
                    ? Center(
                        child: Text(
                          'No conversations yet',
                          style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                        ),
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        itemCount: items.length,
                        itemBuilder: (context, i) {
                          final c = items[i];
                          return ListTile(
                            dense: true,
                            selected: c.id == currentId,
                            selectedTileColor: theme.colorScheme.surfaceContainerHighest,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                            leading: Icon(c.pinned ? Icons.push_pin : Icons.chat_bubble_outline, size: 18),
                            title: Text(c.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                            onTap: () => _go('/chat/${c.id}'),
                            trailing: PopupMenuButton<String>(
                              tooltip: 'Conversation options',
                              icon: const Icon(Icons.more_horiz, size: 20),
                              onSelected: (action) => switch (action) {
                                'rename' => _rename(c),
                                'pin' => _run(
                                  () => ref.read(conversationsProvider.notifier).setPinned(c.id, !c.pinned),
                                ),
                                'export-md' => _export(c, 'markdown'),
                                'export-txt' => _export(c, 'txt'),
                                'delete' => _delete(c),
                                _ => null,
                              },
                              itemBuilder: (context) => [
                                const PopupMenuItem(value: 'rename', child: Text('Rename')),
                                PopupMenuItem(value: 'pin', child: Text(c.pinned ? 'Unpin' : 'Pin')),
                                const PopupMenuItem(value: 'export-md', child: Text('Export as Markdown')),
                                const PopupMenuItem(value: 'export-txt', child: Text('Export as text')),
                                const PopupMenuItem(value: 'delete', child: Text('Delete')),
                              ],
                            ),
                          );
                        },
                      ),
              ),
            ),
            const Divider(height: 1),
            ListTile(
              leading: CircleAvatar(
                backgroundColor: theme.colorScheme.primary,
                foregroundColor: theme.colorScheme.onPrimary,
                child: Text((user?.displayName.isNotEmpty ?? false) ? user!.displayName[0].toUpperCase() : '?'),
              ),
              title: Text(user?.displayName ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
              subtitle: Text(user?.email ?? '', maxLines: 1, overflow: TextOverflow.ellipsis),
              trailing: const Icon(Icons.settings_outlined),
              onTap: () => _go('/settings'),
            ),
          ],
        ),
      ),
    );
  }
}
