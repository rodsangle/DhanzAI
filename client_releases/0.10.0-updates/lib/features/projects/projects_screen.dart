import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../models/models.dart';
import 'projects_controller.dart';

/// Create, edit and delete project workspaces.
class ProjectsScreen extends ConsumerWidget {
  const ProjectsScreen({super.key});

  Future<void> _edit(BuildContext context, WidgetRef ref, [Project? project]) async {
    final result = await showDialog<_ProjectForm>(
      context: context,
      builder: (context) => _ProjectDialog(project: project),
    );
    if (result == null || !context.mounted) return;
    final controller = ref.read(projectsProvider.notifier);
    try {
      if (project == null) {
        final created = await controller.create(
          result.name,
          description: result.description,
          instructions: result.instructions,
        );
        ref.read(selectedProjectProvider.notifier).select(created.id);
      } else {
        await controller.save(
          project.id,
          name: result.name,
          description: result.description,
          instructions: result.instructions,
        );
      }
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref, Project project) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete “${project.name}”?'),
        content: const Text('Its chats and documents are kept and moved out of the project.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete project')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    try {
      await ref.read(projectsProvider.notifier).delete(project.id);
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final projects = ref.watch(projectsProvider);
    final selected = ref.watch(selectedProjectProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Projects'),
        leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _edit(context, ref),
        icon: const Icon(Icons.create_new_folder_outlined),
        label: const Text('New project'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 820),
          child: projects.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('Could not load projects: $e')),
            data: (items) => items.isEmpty
                ? Center(
                    child: Padding(
                      padding: const EdgeInsets.all(32),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.folder_outlined, size: 48, color: theme.colorScheme.primary),
                          const SizedBox(height: 12),
                          Text('No projects yet', style: theme.textTheme.titleMedium),
                          const SizedBox(height: 6),
                          Text(
                            'Projects keep related chats and documents together, and can give Dhanz '
                            'standing instructions such as “use metric units” or “answer as a design engineer”.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                          ),
                        ],
                      ),
                    ),
                  )
                : ListView(
                    padding: const EdgeInsets.fromLTRB(8, 8, 8, 96),
                    children: [
                      for (final p in items)
                        Card(
                          child: ListTile(
                            leading: Icon(
                              selected == p.id ? Icons.folder_open : Icons.folder_outlined,
                              color: theme.colorScheme.primary,
                            ),
                            title: Text(p.name),
                            subtitle: Text(
                              [
                                if ((p.description ?? '').isNotEmpty) p.description!,
                                if ((p.instructions ?? '').isNotEmpty) 'Instructions: ${p.instructions!}',
                              ].join('\n'),
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                            ),
                            onTap: () {
                              ref.read(selectedProjectProvider.notifier).select(p.id);
                              context.go('/chat');
                            },
                            trailing: PopupMenuButton<String>(
                              tooltip: 'Project options',
                              onSelected: (a) => a == 'edit' ? _edit(context, ref, p) : _delete(context, ref, p),
                              itemBuilder: (context) => const [
                                PopupMenuItem(value: 'edit', child: Text('Edit')),
                                PopupMenuItem(value: 'delete', child: Text('Delete')),
                              ],
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

typedef _ProjectForm = ({String name, String description, String instructions});

class _ProjectDialog extends StatefulWidget {
  const _ProjectDialog({this.project});

  final Project? project;

  @override
  State<_ProjectDialog> createState() => _ProjectDialogState();
}

class _ProjectDialogState extends State<_ProjectDialog> {
  late final _name = TextEditingController(text: widget.project?.name);
  late final _description = TextEditingController(text: widget.project?.description);
  late final _instructions = TextEditingController(text: widget.project?.instructions);

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _instructions.dispose();
    super.dispose();
  }

  void _submit() {
    if (_name.text.trim().isEmpty) return;
    Navigator.pop<_ProjectForm>(context, (
      name: _name.text.trim(),
      description: _description.text.trim(),
      instructions: _instructions.text.trim(),
    ));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.project == null ? 'New project' : 'Edit project'),
      content: SizedBox(
        width: 520,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _name,
                autofocus: true,
                maxLength: 120,
                decoration: const InputDecoration(labelText: 'Name'),
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _description,
                maxLines: 2,
                decoration: const InputDecoration(labelText: 'Description (optional)'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _instructions,
                minLines: 3,
                maxLines: 6,
                maxLength: 8000,
                decoration: const InputDecoration(
                  labelText: 'Instructions for Dhanz (optional)',
                  hintText: 'e.g. Use metric units. Our plant runs 3 shifts. Answer as a maintenance engineer.',
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _submit, child: const Text('Save')),
      ],
    );
  }
}
