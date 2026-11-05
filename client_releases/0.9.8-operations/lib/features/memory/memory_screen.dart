import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../auth/auth_controller.dart';

class MemoriesController extends AsyncNotifier<List<Memory>> {
  @override
  Future<List<Memory>> build() async {
    final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
    if (userId == null) return const [];
    return ref.read(apiClientProvider).memories();
  }

  Future<void> add(String content) async {
    final memory = await ref.read(apiClientProvider).addMemory(content);
    state = AsyncData([...state.value ?? const <Memory>[], memory]);
  }

  Future<void> edit(String id, String content) async {
    final updated = await ref.read(apiClientProvider).editMemory(id, content);
    state = AsyncData([for (final m in state.value ?? const <Memory>[]) m.id == id ? updated : m]);
  }

  Future<void> remove(String id) async {
    await ref.read(apiClientProvider).deleteMemory(id);
    state = AsyncData([
      for (final m in state.value ?? const <Memory>[])
        if (m.id != id) m,
    ]);
  }

  Future<void> clear() async {
    await ref.read(apiClientProvider).deleteAllMemories();
    state = const AsyncData([]);
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }
}

final memoriesProvider = AsyncNotifierProvider<MemoriesController, List<Memory>>(MemoriesController.new);

/// View, add, edit and delete what Dhanz remembers; turn memory on or off.
class MemoryScreen extends ConsumerWidget {
  const MemoryScreen({super.key});

  static final _date = DateFormat.yMMMd();

  Future<void> _guard(BuildContext context, Future<void> Function() action) async {
    try {
      await action();
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final user = ref.watch(authControllerProvider).value;
    final memories = ref.watch(memoriesProvider);
    final enabled = user?.memoryEnabled ?? false;
    final controller = ref.read(memoriesProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Memory'),
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/settings'),
        ),
        actions: [
          if ((memories.value ?? const []).isNotEmpty)
            IconButton(
              tooltip: 'Forget everything',
              icon: const Icon(Icons.delete_sweep_outlined),
              onPressed: () async {
                final ok = await showDialog<bool>(
                  context: context,
                  builder: (context) => AlertDialog(
                    title: const Text('Forget everything?'),
                    content: const Text('All saved memories will be deleted.'),
                    actions: [
                      TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                      FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete all')),
                    ],
                  ),
                );
                if (ok == true && context.mounted) await _guard(context, controller.clear);
              },
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () async {
          final text = await showTextPrompt(
            context,
            title: 'Add a memory',
            confirmLabel: 'Remember',
            hint: 'e.g. I prefer answers in metric units',
            maxLines: 3,
            maxLength: 1000,
          );
          if (text != null && text.trim().isNotEmpty && context.mounted) {
            await _guard(context, () => controller.add(text.trim()));
          }
        },
        icon: const Icon(Icons.add),
        label: const Text('Add memory'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 96),
            children: [
              SwitchListTile(
                secondary: const Icon(Icons.psychology_outlined),
                title: const Text('Let Dhanz remember things'),
                subtitle: const Text(
                  'Saved memories are added to every conversation. Say “Remember that …” in a chat, or add '
                  'them here. Memory is off unless you turn it on.',
                ),
                value: enabled,
                onChanged: (v) => _guard(context, () async {
                  final updated = await ref.read(apiClientProvider).updateMe(memoryEnabled: v);
                  ref.read(authControllerProvider.notifier).updateUser(updated);
                }),
              ),
              const Divider(),
              memories.when(
                loading: () => const Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(child: CircularProgressIndicator()),
                ),
                error: (e, _) => ListTile(title: Text('Could not load memories: $e')),
                data: (items) => items.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(32),
                        child: Text(
                          'Nothing saved yet.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                        ),
                      )
                    : Column(
                        children: [
                          for (final m in items)
                            ListTile(
                              leading: Icon(
                                m.source == 'chat' ? Icons.chat_bubble_outline : Icons.edit_note,
                                color: enabled ? theme.colorScheme.primary : theme.disabledColor,
                              ),
                              title: Text(m.content),
                              subtitle: Text(
                                '${m.source == 'chat' ? 'From a chat' : 'Added by you'} · ${_date.format(m.createdAt)}',
                              ),
                              onTap: () async {
                                final text = await showTextPrompt(
                                  context,
                                  title: 'Edit memory',
                                  confirmLabel: 'Save',
                                  initialText: m.content,
                                  maxLines: 3,
                                  maxLength: 1000,
                                );
                                if (text != null && text.trim().isNotEmpty && context.mounted) {
                                  await _guard(context, () => controller.edit(m.id, text.trim()));
                                }
                              },
                              trailing: IconButton(
                                tooltip: 'Forget this',
                                icon: const Icon(Icons.delete_outline),
                                onPressed: () => _guard(context, () => controller.remove(m.id)),
                              ),
                            ),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
