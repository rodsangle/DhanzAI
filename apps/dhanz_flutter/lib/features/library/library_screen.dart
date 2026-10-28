import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../auth/auth_controller.dart';
import '../conversations/conversations_controller.dart';

class LibraryController extends AsyncNotifier<List<KnowledgeDocument>> {
  @override
  Future<List<KnowledgeDocument>> build() async {
    final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
    if (userId == null) return const [];
    return ref.read(apiClientProvider).documents();
  }

  Future<void> add(String url) async {
    final doc = await ref.read(apiClientProvider).addDocument(url);
    final current = state.value ?? const [];
    state = AsyncData([
      doc,
      for (final d in current)
        if (d.id != doc.id) d,
    ]);
  }

  Future<void> remove(String id) async {
    await ref.read(apiClientProvider).deleteDocument(id);
    state = AsyncData([
      for (final d in state.value ?? const <KnowledgeDocument>[])
        if (d.id != id) d,
    ]);
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }
}

final libraryProvider = AsyncNotifierProvider<LibraryController, List<KnowledgeDocument>>(LibraryController.new);

/// The user's private knowledge library: pages Dhanz can look up and cite.
class LibraryScreen extends ConsumerStatefulWidget {
  const LibraryScreen({super.key});

  @override
  ConsumerState<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends ConsumerState<LibraryScreen> {
  final _search = TextEditingController();
  Timer? _debounce;
  List<LibraryHit>? _hits;
  bool _searching = false;

  static final _date = DateFormat.yMMMd();

  @override
  void dispose() {
    _search.dispose();
    _debounce?.cancel();
    super.dispose();
  }

  void _snack(String text) => ScaffoldMessenger.of(context)
    ..clearSnackBars() // newest status replaces any queued one
    ..showSnackBar(SnackBar(content: Text(text)));

  void _onSearchChanged(String q) {
    _debounce?.cancel();
    if (q.trim().isEmpty) {
      setState(() => _hits = null);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 400), () async {
      setState(() => _searching = true);
      try {
        final hits = await ref.read(apiClientProvider).searchLibrary(q.trim());
        if (mounted && _search.text.trim() == q.trim()) setState(() => _hits = hits);
      } on ApiException catch (e) {
        if (mounted) _snack(e.message);
      } finally {
        if (mounted) setState(() => _searching = false);
      }
    });
  }

  Future<void> _addUrl() async {
    final url = await showTextPrompt(
      context,
      title: 'Add a web page',
      confirmLabel: 'Add',
      hint: 'https://…',
      prefixIcon: Icons.link,
      keyboardType: TextInputType.url,
      help: const Text(
        'Dhanz reads public pages only. Pages behind a login or paywall, or that ask '
        'automated readers not to visit (robots.txt), are not added.',
        style: TextStyle(fontSize: 12),
      ),
    );
    if (url == null || url.trim().isEmpty) return;
    final normalized = url.trim().startsWith('http') ? url.trim() : 'https://${url.trim()}';
    if (!mounted) return;
    _snack('Reading $normalized…');
    try {
      await ref.read(libraryProvider.notifier).add(normalized);
      if (mounted) _snack('Added to your library');
    } on ApiException catch (e) {
      if (mounted) _snack(e.message);
    }
  }

  Future<void> _delete(KnowledgeDocument d) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove from library?'),
        content: Text('"${d.title}" will no longer be used to answer your questions.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(libraryProvider.notifier).remove(d.id);
    } on ApiException catch (e) {
      if (mounted) _snack(e.message);
    }
  }

  Future<void> _open(String url) async {
    final uri = Uri.tryParse(url);
    if (uri != null) await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _preview(KnowledgeDocument d) async {
    try {
      final full = await ref.read(apiClientProvider).document(d.id);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(full.title),
          content: SizedBox(
            width: 640,
            height: 460,
            child: SingleChildScrollView(child: SelectableText(full.content ?? '')),
          ),
          actions: [
            TextButton(onPressed: () => _open(full.url), child: const Text('Open page')),
            FilledButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
          ],
        ),
      );
    } on ApiException catch (e) {
      if (mounted) _snack(e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final docs = ref.watch(libraryProvider);
    final features = ref.watch(serverInfoProvider).value?.features;
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Knowledge library'),
        leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addUrl,
        icon: const Icon(Icons.add_link),
        label: const Text('Add page'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                child: Text(
                  'Pages you add here, and pages Dhanz reads during web research, are searched when you chat. '
                  'Only you can see your library. '
                  '${features?.semanticSearch == true ? 'Semantic search is on.' : 'Keyword search is used (no embedding model configured).'}',
                  style: muted,
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                child: TextField(
                  controller: _search,
                  onChanged: _onSearchChanged,
                  decoration: InputDecoration(
                    hintText: 'Search your library',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: _searching
                        ? const Padding(
                            padding: EdgeInsets.all(14),
                            child: SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                          )
                        : null,
                  ),
                ),
              ),
              Expanded(
                child: _hits != null
                    ? _hits!.isEmpty
                          ? Center(child: Text('No matching passages', style: muted))
                          : ListView(
                              padding: const EdgeInsets.fromLTRB(8, 0, 8, 96),
                              children: [
                                for (final h in _hits!)
                                  ListTile(
                                    leading: const Icon(Icons.format_quote),
                                    title: Text(h.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                                    subtitle: Text(h.snippet, maxLines: 3, overflow: TextOverflow.ellipsis),
                                    onTap: () => _open(h.url),
                                  ),
                              ],
                            )
                    : docs.when(
                        loading: () => const Center(child: CircularProgressIndicator()),
                        error: (e, _) => Center(
                          child: TextButton.icon(
                            onPressed: () => ref.read(libraryProvider.notifier).refresh(),
                            icon: const Icon(Icons.refresh),
                            label: const Text('Could not load your library. Retry'),
                          ),
                        ),
                        data: (items) => items.isEmpty
                            ? Center(
                                child: Padding(
                                  padding: const EdgeInsets.all(32),
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(Icons.local_library_outlined, size: 48, color: theme.colorScheme.primary),
                                      const SizedBox(height: 12),
                                      Text('Your library is empty', style: theme.textTheme.titleMedium),
                                      const SizedBox(height: 6),
                                      Text(
                                        'Add a web page, or ask Dhanz a question that needs the web.',
                                        style: muted,
                                        textAlign: TextAlign.center,
                                      ),
                                    ],
                                  ),
                                ),
                              )
                            : ListView.builder(
                                padding: const EdgeInsets.fromLTRB(8, 0, 8, 96),
                                itemCount: items.length,
                                itemBuilder: (context, i) {
                                  final d = items[i];
                                  return ListTile(
                                    leading: Icon(
                                      d.addedVia == 'research' ? Icons.travel_explore : Icons.bookmark_outline,
                                      color: theme.colorScheme.primary,
                                    ),
                                    title: Text(d.title, maxLines: 1, overflow: TextOverflow.ellipsis),
                                    subtitle: Text(
                                      [
                                        d.siteName ?? d.host,
                                        if (d.publishedAt != null) 'published ${_date.format(d.publishedAt!)}',
                                        'retrieved ${_date.format(d.retrievedAt)}',
                                        if (d.addedVia == 'research') 'saved from research',
                                      ].join(' · '),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                    onTap: () => _preview(d),
                                    trailing: PopupMenuButton<String>(
                                      tooltip: 'Document options',
                                      onSelected: (a) => a == 'open' ? _open(d.url) : _delete(d),
                                      itemBuilder: (context) => const [
                                        PopupMenuItem(value: 'open', child: Text('Open page')),
                                        PopupMenuItem(value: 'delete', child: Text('Remove')),
                                      ],
                                    ),
                                  );
                                },
                              ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
