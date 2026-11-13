import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../chat/markdown_view.dart';
import 'conversations_controller.dart';

String _date(String? iso) {
  final d = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
  if (d == null) return '';
  return '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

Future<void> _copyLink(BuildContext context, String url) async {
  await Clipboard.setData(ClipboardData(text: url));
  if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Link copied')));
}

/// Create a public read-only link to a chat as it is now; copy or revoke it.
class ShareChatDialog extends ConsumerStatefulWidget {
  const ShareChatDialog({super.key, required this.conversationId});

  final String conversationId;

  @override
  ConsumerState<ShareChatDialog> createState() => _ShareChatDialogState();
}

class _ShareChatDialogState extends ConsumerState<ShareChatDialog> {
  Map<String, dynamic>? _share;
  bool _busy = false;
  String? _error;

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = ref.read(apiClientProvider);
    final share = _share;
    final url = share == null ? null : api.sharedConversationUrl(share['token'] as String);
    return AlertDialog(
      title: const Text('Share chat'),
      content: SizedBox(
        width: 460,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Anyone with the link can read this chat as it is now. Messages you send later are not shared. '
              'Attached files, tool details and your name are never included.',
            ),
            if (url != null) ...[
              const SizedBox(height: 16),
              SelectableText(url, key: const ValueKey('share-url')),
              const SizedBox(height: 4),
              Text('${share!['message_count']} messages shared', style: Theme.of(context).textTheme.bodySmall),
            ],
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
          ],
        ),
      ),
      actions: [
        if (url != null)
          TextButton(
            onPressed: _busy
                ? null
                : () => _run(() async {
                    await api.revokeSharedLink(share!['token'] as String);
                    if (mounted) setState(() => _share = null);
                  }),
            child: const Text('Revoke link'),
          ),
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        if (url == null)
          FilledButton(
            onPressed: _busy
                ? null
                : () => _run(() async {
                    final created = await api.shareConversation(widget.conversationId);
                    if (mounted) setState(() => _share = created);
                  }),
            child: const Text('Create link'),
          )
        else
          FilledButton.icon(
            onPressed: () => _copyLink(context, url),
            icon: const Icon(Icons.copy_rounded, size: 18),
            label: const Text('Copy link'),
          ),
      ],
    );
  }
}

final _sharedLinksProvider = FutureProvider.autoDispose<List<Map<String, dynamic>>>(
  (ref) => ref.read(apiClientProvider).sharedLinks(),
);

/// Settings → Shared links: every public link, with copy and revoke.
class SharedLinksScreen extends ConsumerWidget {
  const SharedLinksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final links = ref.watch(_sharedLinksProvider);
    final api = ref.read(apiClientProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Shared links'),
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/settings'),
        ),
      ),
      body: links.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e is ApiException ? e.message : 'Could not load shared links.')),
        data: (items) => items.isEmpty
            ? const Center(child: Text('You have not shared any chats.'))
            : ListView(
                children: [
                  for (final link in items)
                    ListTile(
                      leading: const Icon(Icons.link),
                      title: Text(link['title'] as String, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                        'Shared ${_date(link['created_at'] as String?)} · ${link['message_count']} messages',
                      ),
                      trailing: Wrap(
                        children: [
                          IconButton(
                            tooltip: 'Copy link',
                            icon: const Icon(Icons.copy_rounded),
                            onPressed: () => _copyLink(context, api.sharedConversationUrl(link['token'] as String)),
                          ),
                          IconButton(
                            tooltip: 'Revoke link',
                            icon: const Icon(Icons.link_off),
                            onPressed: () async {
                              try {
                                await api.revokeSharedLink(link['token'] as String);
                                ref.invalidate(_sharedLinksProvider);
                              } on ApiException catch (e) {
                                if (context.mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                                }
                              }
                            },
                          ),
                        ],
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}

/// Settings → Archived chats: open or restore them.
class ArchivedChatsScreen extends ConsumerWidget {
  const ArchivedChatsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final archived = ref.watch(archivedConversationsProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Archived chats'),
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/settings'),
        ),
      ),
      body: archived.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text(e is ApiException ? e.message : 'Could not load archived chats.')),
        data: (items) => items.isEmpty
            ? const Center(child: Text('No archived chats.'))
            : ListView(
                children: [
                  for (final chat in items)
                    ListTile(
                      leading: const Icon(Icons.archive_outlined),
                      title: Text(chat['title'] as String, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text('Archived ${_date(chat['archived_at'] as String?)}'),
                      onTap: () => context.go('/chat/${chat['id']}'),
                      trailing: TextButton(
                        onPressed: () async {
                          try {
                            await ref.read(conversationsProvider.notifier).unarchive(chat['id'] as String);
                          } on ApiException catch (e) {
                            if (context.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
                            }
                          }
                        },
                        child: const Text('Restore'),
                      ),
                    ),
                ],
              ),
      ),
    );
  }
}

/// The public, read-only page for a shared link. Works without signing in.
class SharedChatScreen extends ConsumerStatefulWidget {
  const SharedChatScreen({super.key, required this.token});

  final String token;

  @override
  ConsumerState<SharedChatScreen> createState() => _SharedChatScreenState();
}

class _SharedChatScreenState extends ConsumerState<SharedChatScreen> {
  late final Future<Map<String, dynamic>> _chat = ref.read(apiClientProvider).sharedConversation(widget.token);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('Shared chat'),
        actions: [TextButton(onPressed: () => context.go('/chat'), child: const Text('Open DHANZ AI'))],
      ),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _chat,
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            final error = snapshot.error;
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  error is ApiException ? error.message : 'Could not load this shared chat.',
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
          final chat = snapshot.data!;
          final messages = (chat['messages'] as List).cast<Map<String, dynamic>>();
          return Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 820),
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Text(chat['title'] as String, style: theme.textTheme.headlineSmall),
                  const SizedBox(height: 4),
                  Text(
                    'Shared ${_date(chat['shared_at'] as String?)} · read only',
                    style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 16),
                  for (final m in messages)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: m['role'] == 'user'
                          ? Align(
                              alignment: Alignment.centerRight,
                              child: Container(
                                constraints: const BoxConstraints(maxWidth: 620),
                                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                decoration: BoxDecoration(
                                  color: theme.colorScheme.secondaryContainer,
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                child: SelectableText(m['content'] as String),
                              ),
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                MarkdownView(m['content'] as String),
                                for (final s in (m['sources'] as List? ?? const []).cast<Map<String, dynamic>>())
                                  Text(
                                    '${s['title']} — ${s['url']}',
                                    style: theme.textTheme.bodySmall,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                if (m['model'] != null)
                                  Text(
                                    m['model'] as String,
                                    style: theme.textTheme.labelSmall?.copyWith(
                                      color: theme.colorScheme.onSurfaceVariant,
                                    ),
                                  ),
                              ],
                            ),
                    ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
