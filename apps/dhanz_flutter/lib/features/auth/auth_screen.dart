import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api/api_client.dart';
import '../../core/providers.dart';
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

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = ref.read(authControllerProvider.notifier);
    try {
      if (_server.text.trim() != ref.read(apiClientProvider).baseUrl) {
        await auth.setServerUrl(_server.text);
      }
      if (widget.register) {
        await auth.register(_email.text, _password.text, _name.text);
      } else {
        await auth.login(_email.text, _password.text);
      }
      // The router redirects to the chat once signed in.
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final register = widget.register;
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
                      const SizedBox(height: 12),
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
