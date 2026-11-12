import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';

/// Enter the 6-digit code emailed at registration. When the server requires a confirmed email,
/// signed-in users land here until it is done.
class VerifyEmailScreen extends ConsumerStatefulWidget {
  const VerifyEmailScreen({super.key});

  @override
  ConsumerState<VerifyEmailScreen> createState() => _VerifyEmailScreenState();
}

class _VerifyEmailScreenState extends ConsumerState<VerifyEmailScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  String? _error;
  String? _info;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _confirm() async {
    if (_code.text.trim().length < 6) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final user = await ref.read(apiClientProvider).confirmEmailCode(_code.text.trim());
      ref.read(authControllerProvider.notifier).updateUser(user);
      if (mounted) context.go('/chat');
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _resend() async {
    setState(() {
      _error = null;
      _info = null;
    });
    try {
      await ref.read(apiClientProvider).sendEmailCode();
      if (mounted) setState(() => _info = 'A new code is on its way. Check your spam folder too.');
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final user = ref.watch(authControllerProvider).value;
    final required = ref.watch(authOptionsProvider).value?.emailVerificationRequired ?? false;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Confirm your email'),
        leading: required
            ? null
            : IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/security')),
        automaticallyImplyLeading: false,
        actions: [
          if (required)
            TextButton(
              onPressed: () => ref.read(authControllerProvider.notifier).logout(),
              child: const Text('Sign out'),
            ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.mark_email_read_outlined, size: 56, color: theme.colorScheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    'We sent a 6-digit code to ${user?.email ?? 'your email'}.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.titleMedium,
                  ),
                  if (required) ...[
                    const SizedBox(height: 8),
                    const Text(
                      'Enter it to start chatting. This keeps automated sign-ups out and lets you recover your account.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                  const SizedBox(height: 24),
                  TextField(
                    controller: _code,
                    autofocus: true,
                    keyboardType: TextInputType.number,
                    autofillHints: const [AutofillHints.oneTimeCode],
                    decoration: const InputDecoration(labelText: 'Code', prefixIcon: Icon(Icons.pin_outlined)),
                    onSubmitted: (_) => _confirm(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      _error!,
                      style: TextStyle(color: theme.colorScheme.error),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  if (_info != null) ...[const SizedBox(height: 12), Text(_info!, textAlign: TextAlign.center)],
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _busy ? null : _confirm,
                    child: _busy
                        ? const SizedBox.square(dimension: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
                        : const Text('Confirm'),
                  ),
                  TextButton(onPressed: _resend, child: const Text('Send a new code')),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
