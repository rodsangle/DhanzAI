import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/platform/social_sign_in.dart';
import '../../core/providers.dart';
import '../../models/models.dart';
import '../../widgets/dhanz_logo.dart';
import 'auth_controller.dart';

/// Sign-in and registration (one screen, two modes).
class AuthScreen extends ConsumerStatefulWidget {
  const AuthScreen({super.key, required this.register});

  final bool register;

  @override
  ConsumerState<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends ConsumerState<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _server = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  bool _showServer = false;
  String? _error;

  /// Set after the password (or Google/Apple) was accepted on an account with two-factor authentication.
  MfaChallenge? _challenge;

  @override
  void initState() {
    super.initState();
    _server.text = ref.read(apiClientProvider).baseUrl;
  }

  @override
  void dispose() {
    for (final c in [_name, _email, _password, _server]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      // The router redirects to the chat once signed in.
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } on SocialSignInException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _applyServer() async {
    if (_server.text.trim() != ref.read(apiClientProvider).baseUrl) {
      await ref.read(authControllerProvider.notifier).setServerUrl(_server.text);
    }
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    final auth = ref.read(authControllerProvider.notifier);
    await _run(() async {
      await _applyServer();
      if (widget.register) {
        await auth.register(_email.text, _password.text, _name.text);
      } else {
        final challenge = await auth.login(_email.text, _password.text);
        if (challenge != null && mounted) setState(() => _challenge = challenge);
      }
    });
  }

  Future<void> _social(String provider, AuthOptions options) => _run(() async {
    await _applyServer();
    final challenge = await ref.read(authControllerProvider.notifier).signInWith(provider, options);
    if (challenge != null && mounted) setState(() => _challenge = challenge);
  });

  List<Widget> _socialButtons(AuthOptions options) {
    final social = ref.read(socialSignInProvider);
    final buttons = <Widget>[
      if (social.supports('apple', options))
        OutlinedButton.icon(
          onPressed: _busy ? null : () => _social('apple', options),
          icon: const Icon(Icons.apple),
          label: const Text('Continue with Apple'),
        ),
      if (social.supports('google', options))
        OutlinedButton.icon(
          onPressed: _busy ? null : () => _social('google', options),
          icon: const Text('G', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 18)),
          label: const Text('Continue with Google'),
        ),
    ];
    if (buttons.isEmpty) return const [];
    return [
      for (final b in buttons) ...[b, const SizedBox(height: 10)],
      Row(
        children: [
          const Expanded(child: Divider()),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Text('or with email', style: Theme.of(context).textTheme.bodySmall),
          ),
          const Expanded(child: Divider()),
        ],
      ),
      const SizedBox(height: 14),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final challenge = _challenge;
    if (challenge != null) {
      return MfaStepScreen(challenge: challenge, onBack: () => setState(() => _challenge = null));
    }
    final theme = Theme.of(context);
    final register = widget.register;
    final options = ref.watch(authOptionsProvider).value ?? const AuthOptions();
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go('/welcome'),
        ),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: AutofillGroup(
                child: Form(
                  key: _form,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Center(child: DhanzLogo(size: 72)),
                      const SizedBox(height: 20),
                      Text(
                        register ? 'Create your account' : 'Welcome back',
                        textAlign: TextAlign.center,
                        style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 28),
                      ..._socialButtons(options),
                      if (register) ...[
                        TextFormField(
                          controller: _name,
                          decoration: const InputDecoration(labelText: 'Name', prefixIcon: Icon(Icons.person_outline)),
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.name],
                          validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter your name' : null,
                        ),
                        const SizedBox(height: 14),
                      ],
                      TextFormField(
                        controller: _email,
                        decoration: const InputDecoration(labelText: 'Email', prefixIcon: Icon(Icons.mail_outline)),
                        keyboardType: TextInputType.emailAddress,
                        textInputAction: TextInputAction.next,
                        autofillHints: const [AutofillHints.email],
                        validator: (v) => (v == null || !RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(v.trim()))
                            ? 'Enter a valid email'
                            : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: _password,
                        obscureText: _obscure,
                        decoration: InputDecoration(
                          labelText: 'Password',
                          prefixIcon: const Icon(Icons.lock_outline),
                          helperText: register
                              ? 'At least 10 characters, mixing letters with numbers or symbols'
                              : null,
                          suffixIcon: IconButton(
                            tooltip: _obscure ? 'Show password' : 'Hide password',
                            icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                            onPressed: () => setState(() => _obscure = !_obscure),
                          ),
                        ),
                        autofillHints: [register ? AutofillHints.newPassword : AutofillHints.password],
                        onFieldSubmitted: (_) => _submit(),
                        validator: (v) {
                          if (v == null || v.isEmpty) return 'Enter your password';
                          if (register && v.length < 10) return 'Use at least 10 characters';
                          return null;
                        },
                      ),
                      const SizedBox(height: 8),
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => setState(() => _showServer = !_showServer),
                          icon: Icon(_showServer ? Icons.expand_less : Icons.dns_outlined, size: 18),
                          label: const Text('Server'),
                        ),
                      ),
                      if (_showServer)
                        TextFormField(
                          controller: _server,
                          decoration: const InputDecoration(
                            labelText: 'DHANZ AI server URL',
                            helperText: 'Use https:// for anything other than local development',
                          ),
                          keyboardType: TextInputType.url,
                          validator: (v) => Uri.tryParse(v?.trim() ?? '')?.hasScheme == true ? null : 'Enter a URL',
                        ),
                      if (_error != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          _error!,
                          style: TextStyle(color: theme.colorScheme.error),
                          textAlign: TextAlign.center,
                        ),
                      ],
                      const SizedBox(height: 20),
                      FilledButton(
                        onPressed: _busy ? null : _submit,
                        child: _busy
                            ? const SizedBox.square(dimension: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
                            : Text(register ? 'Create account' : 'Sign in'),
                      ),
                      if (!register)
                        TextButton(
                          onPressed: () => context.go('/reset-password'),
                          child: const Text('Forgot your password?'),
                        ),
                      const SizedBox(height: 4),
                      TextButton(
                        onPressed: () => context.go(register ? '/login' : '/register'),
                        child: Text(register ? 'Already have an account? Sign in' : 'New here? Create an account'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Second sign-in step: the 6-digit code from the authenticator app (or a recovery code).
class MfaStepScreen extends ConsumerStatefulWidget {
  const MfaStepScreen({super.key, required this.challenge, required this.onBack});

  final MfaChallenge challenge;
  final VoidCallback onBack;

  @override
  ConsumerState<MfaStepScreen> createState() => _MfaStepScreenState();
}

class _MfaStepScreenState extends ConsumerState<MfaStepScreen> {
  final _code = TextEditingController();
  bool _busy = false;
  bool _recovery = false;
  String? _error;

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _verify() async {
    if (_code.text.trim().length < 6) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider.notifier).completeMfa(widget.challenge, _code.text);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: widget.onBack),
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Icon(Icons.verified_user_outlined, size: 56, color: theme.colorScheme.primary),
                  const SizedBox(height: 16),
                  Text(
                    'Two-step verification',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _recovery
                        ? 'Enter one of the recovery codes you saved when you turned on two-step verification.'
                        : 'Enter the 6-digit code from your authenticator app.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 24),
                  TextField(
                    controller: _code,
                    autofocus: true,
                    keyboardType: _recovery ? TextInputType.text : TextInputType.number,
                    textCapitalization: TextCapitalization.characters,
                    autofillHints: const [AutofillHints.oneTimeCode],
                    decoration: InputDecoration(
                      labelText: _recovery ? 'Recovery code' : 'Code',
                      prefixIcon: const Icon(Icons.pin_outlined),
                    ),
                    onSubmitted: (_) => _verify(),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(
                      _error!,
                      style: TextStyle(color: theme.colorScheme.error),
                      textAlign: TextAlign.center,
                    ),
                  ],
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _busy ? null : _verify,
                    child: _busy
                        ? const SizedBox.square(dimension: 22, child: CircularProgressIndicator(strokeWidth: 2.5))
                        : const Text('Verify'),
                  ),
                  TextButton(
                    onPressed: () => setState(() {
                      _recovery = !_recovery;
                      _code.clear();
                      _error = null;
                    }),
                    child: Text(_recovery ? 'Use the authenticator app' : 'Lost your phone? Use a recovery code'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
