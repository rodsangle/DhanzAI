import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../auth/auth_controller.dart';
import 'two_factor_dialogs.dart';

/// Devices signed in to this account.
final sessionsProvider = FutureProvider.autoDispose<List<SessionInfo>>(
  (ref) => ref.watch(apiClientProvider).sessions(),
);

/// Google / Apple accounts linked for sign-in.
final identitiesProvider = FutureProvider.autoDispose<List<LinkedIdentity>>(
  (ref) => ref.watch(apiClientProvider).identities(),
);

/// Devices that skip the second sign-in step. Empty on servers without the feature.
final trustedDevicesProvider = FutureProvider.autoDispose<List<TrustedDevice>>((ref) async {
  try {
    return await ref.watch(apiClientProvider).trustedDevices();
  } on ApiException catch (e) {
    if (e.statusCode == 404 || e.statusCode == 405) return const [];
    rethrow;
  }
});

/// Email, two-step verification, password, linked accounts and signed-in devices.
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

  /// Asks for the second-step code. Email-code accounts get a fresh code emailed first.
  Future<String?> _askCode(
    BuildContext context,
    WidgetRef ref,
    User user,
    String title,
    String confirmLabel, {
    bool destructive = false,
  }) async {
    var help = 'A recovery code works too.';
    if (user.mfaByEmail) {
      try {
        help = '${await ref.read(apiClientProvider).mfaEmailCode()} A recovery code works too.';
      } on ApiException catch (e) {
        help = '${e.message} A recovery code works too.';
      }
      if (!context.mounted) return null;
    }
    return showTextPrompt(
      context,
      title: title,
      confirmLabel: confirmLabel,
      destructive: destructive,
      label: user.mfaByEmail ? 'Code we emailed you' : 'Code from your authenticator app',
      help: Text(help),
      prefixIcon: Icons.pin_outlined,
    );
  }

  Future<void> _enableMfa(BuildContext context, WidgetRef ref, User user) async {
    final on = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => TwoFactorSetupDialog(
        hasPassword: user.hasPassword,
        emailAvailable: (ref.read(authOptionsProvider).value?.mfaEmail ?? false) && user.emailVerified,
      ),
    );
    if (on == true && context.mounted) {
      ref.read(authControllerProvider.notifier).updateUser(await ref.read(apiClientProvider).me());
      ref.invalidate(sessionsProvider);
      if (context.mounted) _snack(context, 'Two-step verification is on. Other devices were signed out.');
    }
  }

  Future<void> _disableMfa(BuildContext context, WidgetRef ref, User user) async {
    final code = await _askCode(context, ref, user, 'Turn off two-step verification?', 'Turn off', destructive: true);
    if (code == null || code.trim().isEmpty || !context.mounted) return;
    try {
      ref.read(authControllerProvider.notifier).updateUser(await ref.read(apiClientProvider).mfaDisable(code.trim()));
      ref.invalidate(trustedDevicesProvider);
      if (context.mounted) _snack(context, 'Two-step verification is off.');
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  Future<void> _newRecoveryCodes(BuildContext context, WidgetRef ref, User user) async {
    final code = await _askCode(context, ref, user, 'New recovery codes', 'Create');
    if (code == null || code.trim().isEmpty || !context.mounted) return;
    try {
      final codes = await ref.read(apiClientProvider).newRecoveryCodes(code.trim());
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialog) => RecoveryCodesDialog(codes: codes, onDone: () => Navigator.pop(dialog)),
      );
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  Future<void> _forgetDevice(BuildContext context, WidgetRef ref, TrustedDevice? device) async {
    try {
      final api = ref.read(apiClientProvider);
      if (device == null) {
        await api.forgetAllTrustedDevices();
      } else {
        await api.forgetTrustedDevice(device.id);
      }
      ref.invalidate(trustedDevicesProvider);
      if (context.mounted) {
        _snack(
          context,
          device == null
              ? 'All devices will ask for the second step again.'
              : '${device.label} will ask for the second step again.',
        );
      }
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  Future<void> _unlink(BuildContext context, WidgetRef ref, LinkedIdentity identity) async {
    try {
      await ref.read(apiClientProvider).unlinkIdentity(identity.provider);
      ref.invalidate(identitiesProvider);
      if (context.mounted) _snack(context, '${identity.providerName} is no longer linked.');
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
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
    final identities = ref.watch(identitiesProvider);
    final trusted = ref.watch(trustedDevicesProvider);
    final user = ref.watch(authControllerProvider).value;
    final options = ref.watch(authOptionsProvider).value ?? const AuthOptions();
    final format = DateFormat.yMMMd().add_jm();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Security'),
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
              if (user != null && !user.emailVerified && options.emailVerification)
                ListTile(
                  leading: Icon(Icons.mark_email_unread_outlined, color: theme.colorScheme.error),
                  title: const Text('Confirm your email'),
                  subtitle: Text('Enter the code we sent to ${user.email}'),
                  onTap: () => context.go('/verify-email'),
                ),
              if (user != null) ...[
                // Hidden on servers without two-step verification (they do not report it).
                if (user.mfaSupported)
                  SwitchListTile(
                    secondary: const Icon(Icons.verified_user_outlined),
                    title: const Text('Two-step verification'),
                    subtitle: Text(
                      !user.mfaEnabled
                          ? (options.mfaEmail
                                ? 'Protect your account with a code from an authenticator app or your email'
                                : 'Protect your account with a code from an authenticator app')
                          : user.mfaByEmail
                          ? 'On: signing in also needs a code we email to you'
                          : 'On: signing in also needs a code from your authenticator app',
                    ),
                    value: user.mfaEnabled,
                    onChanged: (on) => on ? _enableMfa(context, ref, user) : _disableMfa(context, ref, user),
                  ),
                if (user.mfaEnabled)
                  ListTile(
                    leading: const Icon(Icons.key_outlined),
                    title: const Text('New recovery codes'),
                    subtitle: const Text('Replaces your saved codes'),
                    onTap: () => _newRecoveryCodes(context, ref, user),
                  ),
                if (user.mfaEnabled)
                  ...trusted.maybeWhen(
                    data: (devices) => [
                      if (devices.isNotEmpty) ...[
                        const Divider(height: 32),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: Text('Remembered devices', style: theme.textTheme.titleMedium),
                        ),
                        const Padding(
                          padding: EdgeInsets.fromLTRB(16, 4, 16, 0),
                          child: Text('These skip the second sign-in step until they expire.'),
                        ),
                        for (final d in devices)
                          ListTile(
                            leading: const Icon(Icons.devices_outlined),
                            title: Text(d.label),
                            subtitle: Text(
                              'Last used ${format.format(d.lastUsedAt)} · until ${DateFormat.yMMMd().format(d.expiresAt)}',
                            ),
                            trailing: TextButton(
                              onPressed: () => _forgetDevice(context, ref, d),
                              child: const Text('Forget'),
                            ),
                          ),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16),
                          child: OutlinedButton.icon(
                            onPressed: () => _forgetDevice(context, ref, null),
                            icon: const Icon(Icons.phonelink_erase_outlined),
                            label: const Text('Forget all devices'),
                          ),
                        ),
                      ],
                    ],
                    orElse: () => const <Widget>[],
                  ),
                if (user.hasPassword)
                  ListTile(
                    leading: const Icon(Icons.password),
                    title: const Text('Change password'),
                    subtitle: const Text('Signs out your other devices'),
                    onTap: () => _changePassword(context, ref),
                  )
                else
                  const ListTile(
                    leading: Icon(Icons.password),
                    title: Text('No password'),
                    subtitle: Text(
                      'You sign in with Google or Apple. To add a password, use "Forgot your password?" '
                      'on the sign-in screen.',
                    ),
                  ),
              ],
              ...identities.maybeWhen(
                data: (list) => [
                  if (list.isNotEmpty) ...[
                    const Divider(height: 32),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16),
                      child: Text('Linked accounts', style: theme.textTheme.titleMedium),
                    ),
                    for (final identity in list)
                      ListTile(
                        leading: Icon(identity.provider == 'apple' ? Icons.apple : Icons.account_circle_outlined),
                        title: Text(identity.providerName),
                        subtitle: identity.email == null ? null : Text(identity.email!),
                        trailing: TextButton(
                          onPressed: () => _unlink(context, ref, identity),
                          child: const Text('Unlink'),
                        ),
                      ),
                  ],
                ],
                orElse: () => const <Widget>[],
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
