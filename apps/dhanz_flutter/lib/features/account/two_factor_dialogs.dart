import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
import '../../models/models.dart';

/// Turning on two-step verification: password → scan the QR code → type a code → save recovery codes.
/// Pops `true` once it is on.
class TwoFactorSetupDialog extends ConsumerStatefulWidget {
  const TwoFactorSetupDialog({super.key, required this.hasPassword});

  final bool hasPassword;

  @override
  ConsumerState<TwoFactorSetupDialog> createState() => _TwoFactorSetupDialogState();
}

class _TwoFactorSetupDialogState extends ConsumerState<TwoFactorSetupDialog> {
  final _input = TextEditingController();
  MfaSetup? _setup;
  List<String>? _codes;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (!widget.hasPassword) _start();
  }

  @override
  void dispose() {
    _input.dispose();
    super.dispose();
  }

  Future<void> _guard(Future<void> Function() action) async {
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

  Future<void> _start() => _guard(() async {
    final setup = await ref.read(apiClientProvider).mfaSetup(password: widget.hasPassword ? _input.text : null);
    _input.clear();
    setState(() => _setup = setup);
  });

  Future<void> _enable() => _guard(() async {
    final codes = await ref.read(apiClientProvider).mfaEnable(_input.text.trim());
    setState(() => _codes = codes);
  });

  @override
  Widget build(BuildContext context) {
    final codes = _codes;
    if (codes != null) return RecoveryCodesDialog(codes: codes, onDone: () => Navigator.pop(context, true));
    final setup = _setup;
    final theme = Theme.of(context);
    final error = _error == null
        ? const <Widget>[]
        : [const SizedBox(height: 8), Text(_error!, style: TextStyle(color: theme.colorScheme.error))];
    if (setup == null) {
      return AlertDialog(
        title: const Text('Turn on two-step verification'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Signing in will also need a code from an authenticator app on your phone '
              '(Google Authenticator, Microsoft Authenticator, 1Password, ...).',
            ),
            if (widget.hasPassword) ...[
              const SizedBox(height: 16),
              TextField(
                controller: _input,
                obscureText: true,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'Your password'),
                onSubmitted: (_) => _start(),
              ),
            ] else if (_busy)
              const Padding(padding: EdgeInsets.only(top: 16), child: LinearProgressIndicator()),
            ...error,
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          if (widget.hasPassword) FilledButton(onPressed: _busy ? null : _start, child: const Text('Continue')),
        ],
      );
    }
    return AlertDialog(
      title: const Text('Add DHANZ AI to your authenticator'),
      content: SizedBox(
        width: 380,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('1. Scan this QR code with the authenticator app, or enter the key by hand.'),
              const SizedBox(height: 12),
              Center(
                child: Container(
                  color: Colors.white,
                  padding: const EdgeInsets.all(8),
                  child: QrImageView(data: setup.otpauthUri, size: 180, backgroundColor: Colors.white),
                ),
              ),
              const SizedBox(height: 8),
              SelectableText(
                setup.groupedSecret,
                textAlign: TextAlign.center,
                style: theme.textTheme.titleMedium?.copyWith(fontFamily: 'monospace', letterSpacing: 1),
              ),
              Wrap(
                alignment: WrapAlignment.center,
                children: [
                  TextButton.icon(
                    onPressed: () => Clipboard.setData(ClipboardData(text: setup.secret)),
                    icon: const Icon(Icons.copy, size: 18),
                    label: const Text('Copy key'),
                  ),
                  TextButton.icon(
                    onPressed: () => launchUrl(Uri.parse(setup.otpauthUri)),
                    icon: const Icon(Icons.open_in_new, size: 18),
                    label: const Text('Open authenticator app'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text('2. Enter the 6-digit code the app shows.'),
              const SizedBox(height: 8),
              TextField(
                controller: _input,
                autofocus: true,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(labelText: 'Code'),
                onSubmitted: (_) => _enable(),
              ),
              ...error,
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(onPressed: _busy ? null : _enable, child: const Text('Turn on')),
      ],
    );
  }
}

/// Shows recovery codes once, with copy; `onDone` closes.
class RecoveryCodesDialog extends StatelessWidget {
  const RecoveryCodesDialog({super.key, required this.codes, required this.onDone});

  final List<String> codes;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      title: const Text('Save your recovery codes'),
      content: SizedBox(
        width: 380,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'If you lose your phone, each of these codes lets you sign in once. Keep them somewhere safe, '
              'like a password manager. They will not be shown again.',
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(12),
              ),
              child: SelectableText(
                codes.join('\n'),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyLarge?.copyWith(fontFamily: 'monospace', height: 1.6),
              ),
            ),
            TextButton.icon(
              onPressed: () => Clipboard.setData(ClipboardData(text: codes.join('\n'))),
              icon: const Icon(Icons.copy, size: 18),
              label: const Text('Copy all'),
            ),
          ],
        ),
      ),
      actions: [FilledButton(onPressed: onDone, child: const Text('I saved them'))],
    );
  }
}
