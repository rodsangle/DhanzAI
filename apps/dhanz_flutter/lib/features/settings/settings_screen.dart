import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/config.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/dhanz_logo.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../auth/auth_controller.dart';
import '../conversations/conversations_controller.dart';

/// Profile, appearance, AI model preferences, privacy controls and account.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  static const _policies = {
    'balanced': ('Balanced', 'Good answers at a sensible cost'),
    'best': ('Best quality', 'Prefer the most capable models'),
    'cheapest': ('Lowest cost', 'Prefer fast, inexpensive models'),
    'local_first': ('Local first', 'Prefer models running on your own Ollama server'),
  };

  Future<void> _guard(BuildContext context, Future<void> Function() action) async {
    try {
      await action();
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _updateUser(
    BuildContext context,
    WidgetRef ref, {
    String? displayName,
    String? preferredModel,
    String? routingPolicy,
    bool? autoIndexWeb,
  }) {
    return _guard(context, () async {
      final user = await ref
          .read(apiClientProvider)
          .updateMe(
            displayName: displayName,
            preferredModel: preferredModel,
            routingPolicy: routingPolicy,
            autoIndexWeb: autoIndexWeb,
          );
      ref.read(authControllerProvider.notifier).updateUser(user);
    });
  }

  Future<void> _editName(BuildContext context, WidgetRef ref, User user) async {
    final name = await showTextPrompt(
      context,
      title: 'Your name',
      confirmLabel: 'Save',
      initialText: user.displayName,
      maxLength: 100,
    );
    if (name != null && name.trim().isNotEmpty && context.mounted) {
      await _updateUser(context, ref, displayName: name.trim());
    }
  }

  Future<void> _exportData(BuildContext context, WidgetRef ref) => _guard(context, () async {
    final json = await ref.read(apiClientProvider).exportMyData();
    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Your data'),
        content: SizedBox(
          width: 600,
          height: 420,
          child: SingleChildScrollView(
            child: SelectableText(json, style: const TextStyle(fontFamily: 'monospace', fontSize: 12)),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
          FilledButton.icon(
            icon: const Icon(Icons.copy_rounded),
            label: const Text('Copy JSON'),
            onPressed: () async {
              await Clipboard.setData(ClipboardData(text: json));
              if (context.mounted) Navigator.pop(context);
            },
          ),
        ],
      ),
    );
  });

  Future<void> _deleteAccount(BuildContext context, WidgetRef ref) async {
    final password = await showTextPrompt(
      context,
      title: 'Delete account?',
      confirmLabel: 'Delete forever',
      destructive: true,
      obscureText: true,
      label: 'Confirm with your password',
      message: const Text(
        'Your account, conversations and knowledge library will be permanently deleted. This cannot be undone.',
      ),
    );
    if (password != null && password.isNotEmpty && context.mounted) {
      await _guard(context, () => ref.read(authControllerProvider.notifier).deleteAccount(password));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final user = ref.watch(authControllerProvider).value;
    final themeMode = ref.watch(themeModeProvider);
    final models = ref.watch(modelsProvider);
    if (user == null) return const Scaffold(body: Center(child: CircularProgressIndicator()));

    Widget section(String title) => Padding(
      padding: const EdgeInsets.fromLTRB(16, 24, 16, 8),
      child: Text(
        title.toUpperCase(),
        style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.secondary, letterSpacing: 1.2),
      ),
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.only(bottom: 32),
            children: [
              section('Profile'),
              ListTile(
                leading: const Icon(Icons.person_outline),
                title: Text(user.displayName),
                subtitle: Text(user.email),
                trailing: const Icon(Icons.edit_outlined),
                onTap: () => _editName(context, ref, user),
              ),
              section('Appearance'),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: SegmentedButton<ThemeMode>(
                  segments: const [
                    ButtonSegment(value: ThemeMode.dark, icon: Icon(Icons.dark_mode_outlined), label: Text('Dark')),
                    ButtonSegment(value: ThemeMode.light, icon: Icon(Icons.light_mode_outlined), label: Text('Light')),
                    ButtonSegment(value: ThemeMode.system, icon: Icon(Icons.brightness_auto), label: Text('System')),
                  ],
                  selected: {themeMode},
                  onSelectionChanged: (s) => ref.read(themeModeProvider.notifier).set(s.first),
                ),
              ),
              section('AI model'),
              models.when(
                loading: () => const ListTile(title: Text('Loading models…')),
                error: (e, _) => ListTile(title: const Text('Could not load models'), subtitle: Text('$e')),
                data: (list) => list.isEmpty
                    ? const ListTile(
                        leading: Icon(Icons.warning_amber_rounded),
                        title: Text('No AI provider is configured on the server'),
                        subtitle: Text('Ask your administrator to add an OpenAI, Anthropic, Gemini or Ollama key.'),
                      )
                    : ListTile(
                        leading: const Icon(Icons.memory),
                        title: const Text('Default model'),
                        subtitle: const Text('Used unless you pick another model in the chat'),
                        trailing: DropdownButton<String>(
                          value: list.any((m) => m.key == user.preferredModel) ? user.preferredModel : '',
                          underline: const SizedBox.shrink(),
                          items: [
                            const DropdownMenuItem(value: '', child: Text('Automatic')),
                            for (final m in list) DropdownMenuItem(value: m.key, child: Text(m.displayName)),
                          ],
                          onChanged: (v) => _updateUser(context, ref, preferredModel: v ?? ''),
                        ),
                      ),
              ),
              RadioGroup<String>(
                groupValue: user.routingPolicy,
                onChanged: (v) => v == null ? null : _updateUser(context, ref, routingPolicy: v),
                child: Column(
                  children: [
                    for (final e in _policies.entries)
                      RadioListTile<String>(value: e.key, title: Text(e.value.$1), subtitle: Text(e.value.$2)),
                  ],
                ),
              ),
              section('Web research & knowledge'),
              ListTile(
                leading: Icon(
                  (ref.watch(serverInfoProvider).value?.features.webSearch ?? false) ? Icons.public : Icons.public_off,
                ),
                title: const Text('Web search'),
                subtitle: Text(
                  (ref.watch(serverInfoProvider).value?.features.webSearch ?? false)
                      ? 'Available. Choose Auto, Always or Off from the globe button in the chat.'
                      : 'Not configured on this server. Dhanz can still read links you paste.',
                ),
              ),
              SwitchListTile(
                secondary: const Icon(Icons.bookmark_add_outlined),
                title: const Text('Save researched pages to my library'),
                subtitle: const Text('Pages Dhanz reads for you become searchable in your knowledge library'),
                value: user.autoIndexWeb,
                onChanged: (v) => _updateUser(context, ref, autoIndexWeb: v),
              ),
              ListTile(
                leading: const Icon(Icons.local_library_outlined),
                title: const Text('Knowledge library'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.go('/library'),
              ),
              section('Personalisation'),
              ListTile(
                leading: const Icon(Icons.psychology_outlined),
                title: const Text('Memory'),
                subtitle: Text(user.memoryEnabled ? 'On — Dhanz uses what you asked it to remember' : 'Off'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.go('/memory'),
              ),
              ListTile(
                leading: const Icon(Icons.folder_outlined),
                title: const Text('Projects'),
                subtitle: const Text('Workspaces with their own chats, documents and instructions'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.go('/projects'),
              ),
              ListTile(
                leading: const Icon(Icons.mic_none),
                title: const Text('Voice assistant'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.go('/voice'),
              ),
              section('Privacy & data'),
              ListTile(
                leading: const Icon(Icons.download_outlined),
                title: const Text('Export my data'),
                subtitle: const Text('Your profile and every conversation as JSON'),
                onTap: () => _exportData(context, ref),
              ),
              ListTile(
                leading: Icon(Icons.delete_forever_outlined, color: theme.colorScheme.error),
                title: Text('Delete account', style: TextStyle(color: theme.colorScheme.error)),
                subtitle: const Text('Permanently remove your account and conversations'),
                onTap: () => _deleteAccount(context, ref),
              ),
              section('Account'),
              ListTile(
                leading: const Icon(Icons.dns_outlined),
                title: const Text('Server'),
                subtitle: Text(ref.watch(apiClientProvider).baseUrl),
              ),
              ListTile(
                leading: const Icon(Icons.logout),
                title: const Text('Sign out'),
                onTap: () => ref.read(authControllerProvider.notifier).logout(),
              ),
              const SizedBox(height: 24),
              const Center(child: DhanzLogo(size: 40)),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  '${AppConfig.appName} · ${AppConfig.tagline}',
                  style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
