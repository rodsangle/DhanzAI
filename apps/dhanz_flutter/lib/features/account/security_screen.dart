import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';

/// Devices signed in to this account.
final sessionsProvider = FutureProvider.autoDispose<List<SessionInfo>>(
  (ref) => ref.watch(apiClientProvider).sessions(),
);

/// Password and signed-in devices.
class SecurityScreen extends ConsumerWidget {
  const SecurityScreen({super.key});

  void _snack(BuildContext context, String text) => ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(SnackBar(content: Text(text)));

  Future<void> _changePassword(BuildContext context, WidgetRef ref) async {
    final changed = await showDialog<bool>(context: context, builder: (_) => const ChangePasswordDialog());
    if (changed == true && context.mounted) {
      _snack(context, 'Password changed. Other devices have been signed out.');
      ref.invalidate(sessionsProvider);
    }
  }

  Future<void> _revoke(BuildContext context, WidgetRef ref, SessionInfo s) async {
    try {
      await ref.read(apiClientProvider).revokeSession(s.id);
      ref.invalidate(sessionsProvider);
      if (context.mounted) _snack(context, '${s.deviceName} has been signed out.');
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  Future<void> _revokeOthers(BuildContext context, WidgetRef ref) async {
    try {
      final n = await ref.read(apiClientProvider).revokeOtherSessions();
      ref.invalidate(sessionsProvider);
      if (context.mounted) {
        _snack(context, n == 0 ? 'No other devices were signed in.' : 'Signed out $n other devices.');
      }
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final sessions = ref.watch(sessionsProvider);
    final format = DateFormat.yMMMd().add_jm();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Password & devices'),
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/settings'),
        ),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.symmetric(vertical: 16),
            children: [
              ListTile(
                leading: const Icon(Icons.password),
                title: const Text('Change password'),
                subtitle: const Text('Signs out your other devices'),
                onTap: () => _changePassword(context, ref),
              ),
              const Divider(height: 32),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text('Signed-in devices', style: theme.textTheme.titleMedium),
              ),
              ...sessions.when(
                loading: () => [const Padding(padding: EdgeInsets.all(24), child: LinearProgressIndicator())],
                error: (e, _) => [ListTile(title: const Text('Could not load devices'), subtitle: Text('$e'))],
                data: (list) => [
                  for (final s in list)
                    ListTile(
                      leading: Icon(s.current ? Icons.smartphone : Icons.devices_other),
                      title: Text(s.current ? '${s.deviceName} (this device)' : s.deviceName),
                      subtitle: Text(
                        'Signed in ${format.format(s.createdAt.toLocal())} · '
                        'last active ${format.format(s.lastUsedAt.toLocal())}',
                      ),
                      trailing: s.current
                          ? null
                          : TextButton(onPressed: () => _revoke(context, ref, s), child: const Text('Sign out')),
                    ),
                  if (list.where((s) => !s.current).isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.all(16),
                      child: OutlinedButton.icon(
                        onPressed: () => _revokeOthers(context, ref),
                        icon: const Icon(Icons.logout),
                        label: const Text('Sign out all other devices'),
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
}

/// Current + new password. Pops `true` when the password was changed.
class ChangePasswordDialog extends ConsumerStatefulWidget {
  const ChangePasswordDialog({super.key});

  @override
  ConsumerState<ChangePasswordDialog> createState() => _ChangePasswordDialogState();
}

class _ChangePasswordDialogState extends ConsumerState<ChangePasswordDialog> {
  final _form = GlobalKey<FormState>();
  final _current = TextEditingController();
  final _next = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _current.dispose();
    _next.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(apiClientProvider).changePassword(_current.text, _next.text);
      if (mounted) Navigator.pop(context, true);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Change password'),
      content: Form(
        key: _form,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextFormField(
              controller: _current,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'Current password'),
              autofillHints: const [AutofillHints.password],
              validator: (v) => (v == null || v.isEmpty) ? 'Enter your current password' : null,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _next,
              obscureText: true,
              decoration: const InputDecoration(labelText: 'New password', helperText: 'At least 10 characters'),
              autofillHints: const [AutofillHints.newPassword],
              validator: (v) => (v == null || v.length < 10) ? 'Use at least 10 characters' : null,
              onFieldSubmitted: (_) => _submit(),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(onPressed: _busy ? null : () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _busy ? null : _submit, child: const Text('Change password')),
      ],
    );
  }
}
