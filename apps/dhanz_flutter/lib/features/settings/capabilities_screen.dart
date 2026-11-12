import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/providers.dart';
import '../auth/auth_controller.dart';

final assistantCapabilitiesProvider = FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  ref.watch(authControllerProvider.select((state) => state.value?.id));
  final api = ref.watch(apiClientProvider);
  final results = await Future.wait([api.assistantCapabilities(), api.assistantSkills()]);
  return {...results[0] as Map<String, dynamic>, 'skills': results[1]};
});

class CapabilitiesScreen extends ConsumerWidget {
  const CapabilitiesScreen({super.key});

  Future<void> _edit(BuildContext context, WidgetRef ref, Map<String, dynamic>? skill) => showDialog<void>(
    context: context,
    builder: (_) => _SkillEditor(skill: skill, onSaved: () => ref.invalidate(assistantCapabilitiesProvider)),
  );

  @override
  Widget build(BuildContext context, WidgetRef ref) => Scaffold(
    appBar: AppBar(
      leading: IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/settings')),
      title: const Text('Capabilities and skills'),
      actions: [
        IconButton(
          tooltip: 'Refresh capabilities',
          onPressed: () => ref.invalidate(assistantCapabilitiesProvider),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: ref
        .watch(assistantCapabilitiesProvider)
        .when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('$error'),
                TextButton(onPressed: () => ref.invalidate(assistantCapabilitiesProvider), child: const Text('Retry')),
              ],
            ),
          ),
          data: (data) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Live capabilities', style: Theme.of(context).textTheme.titleLarge),
              for (final item in (data['capabilities'] as List).cast<Map<String, dynamic>>())
                ListTile(
                  leading: Icon(
                    item['status'] == 'available'
                        ? Icons.check_circle_outline
                        : item['status'] == 'requires_connection'
                        ? Icons.link
                        : Icons.block,
                  ),
                  title: Text(
                    '${item['name']} · ${switch (item['status']) {
                      'available' => 'Available',
                      'requires_connection' => 'Requires connection',
                      _ => 'Unavailable',
                    }}',
                  ),
                  subtitle: Text('${item['details']}'),
                ),
              Text('${data['sharing']}'),
              const Divider(height: 32),
              Row(
                children: [
                  Expanded(child: Text('Your reusable skills', style: Theme.of(context).textTheme.titleLarge)),
                  FilledButton.icon(
                    onPressed: () => _edit(context, ref, null),
                    icon: const Icon(Icons.add),
                    label: const Text('Create skill'),
                  ),
                ],
              ),
              const Text(
                'Dhanz reads relevant enabled skills before using them. Skills do not grant new app permissions.',
              ),
              for (final skill in (data['skills'] as List).cast<Map<String, dynamic>>())
                ListTile(
                  title: Text('${skill['name']}${skill['enabled'] == true ? '' : ' · Disabled'}'),
                  subtitle: Text('${skill['description']}'),
                  onTap: () => _edit(context, ref, skill),
                  trailing: skill['builtin'] == true
                      ? const Icon(Icons.auto_awesome_outlined)
                      : IconButton(
                          tooltip: 'Delete skill',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () async {
                            final confirmed = await showDialog<bool>(
                              context: context,
                              builder: (context) => AlertDialog(
                                title: Text('Delete ${skill['name']}?'),
                                actions: [
                                  TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
                                  FilledButton(
                                    onPressed: () => Navigator.pop(context, true),
                                    child: const Text('Delete'),
                                  ),
                                ],
                              ),
                            );
                            if (confirmed != true) return;
                            try {
                              await ref.read(apiClientProvider).deleteAssistantSkill(skill['name'] as String);
                              ref.invalidate(assistantCapabilitiesProvider);
                            } on Object catch (e) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
                              }
                            }
                          },
                        ),
                ),
            ],
          ),
        ),
  );
}

class _SkillEditor extends ConsumerStatefulWidget {
  const _SkillEditor({required this.skill, required this.onSaved});
  final Map<String, dynamic>? skill;
  final VoidCallback onSaved;
  @override
  ConsumerState<_SkillEditor> createState() => _SkillEditorState();
}

class _SkillEditorState extends ConsumerState<_SkillEditor> {
  late final TextEditingController name;
  late final TextEditingController description;
  late final TextEditingController instructions;
  late bool enabled;
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    name = TextEditingController(text: widget.skill?['name'] as String?);
    description = TextEditingController(text: widget.skill?['description'] as String?);
    instructions = TextEditingController(text: widget.skill?['instructions'] as String?);
    enabled = widget.skill?['enabled'] as bool? ?? true;
  }

  @override
  void dispose() {
    name.dispose();
    description.dispose();
    instructions.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.skill == null ? 'Create reusable skill' : 'Edit skill'),
    content: SizedBox(
      width: 600,
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: name,
              enabled: widget.skill == null && !busy,
              maxLength: 64,
              decoration: const InputDecoration(labelText: 'Skill name', hintText: 'weekly-research-report'),
            ),
            TextField(
              controller: description,
              enabled: !busy,
              maxLength: 500,
              maxLines: 2,
              decoration: const InputDecoration(labelText: 'When to use this skill'),
            ),
            TextField(
              controller: instructions,
              enabled: !busy,
              maxLength: 12000,
              minLines: 5,
              maxLines: 10,
              decoration: const InputDecoration(
                labelText: 'Instructions',
                helperText: 'Task steps and expected result. Never include credentials.',
              ),
            ),
            SwitchListTile(
              title: const Text('Use automatically when relevant'),
              value: enabled,
              onChanged: busy ? null : (value) => setState(() => enabled = value),
            ),
            if (error != null) Text(error!),
          ],
        ),
      ),
    ),
    actions: [
      TextButton(onPressed: busy ? null : () => Navigator.pop(context), child: const Text('Cancel')),
      FilledButton(
        onPressed: busy
            ? null
            : () async {
                setState(() {
                  busy = true;
                  error = null;
                });
                try {
                  await ref.read(apiClientProvider).saveAssistantSkill({
                    'name': name.text.trim(),
                    'description': description.text.trim(),
                    'instructions': instructions.text.trim(),
                    'enabled': enabled,
                  });
                  widget.onSaved();
                  if (context.mounted) Navigator.pop(context);
                } on Object catch (e) {
                  if (context.mounted) {
                    setState(() {
                      busy = false;
                      error = '$e';
                    });
                  }
                }
              },
        child: const Text('Save skill'),
      ),
    ],
  );
}
