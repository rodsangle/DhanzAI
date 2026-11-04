import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../widgets/dhanz_logo.dart';

class WelcomeScreen extends StatelessWidget {
  const WelcomeScreen({super.key});

  static const _features = [
    (Icons.chat_bubble_outline, 'Chat naturally', 'Multi-turn conversations with streaming answers.'),
    (Icons.hub_outlined, 'Many AI models', 'OpenAI, Claude, Gemini or local Ollama models — picked for the task.'),
    (Icons.verified_outlined, 'Honest by design', 'Dhanz separates facts from estimates and never invents sources.'),
    (Icons.lock_outline, 'Private', 'Your conversations are yours. Export or delete them any time.'),
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SizedBox(height: 12),
                  const Center(child: DhanzBrandHeader(logoSize: 104)),
                  const SizedBox(height: 36),
                  for (final (icon, title, body) in _features)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 16),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: theme.colorScheme.surfaceContainerHigh,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(icon, color: theme.colorScheme.primary),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(title, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
                                const SizedBox(height: 2),
                                Text(
                                  body,
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  const SizedBox(height: 24),
                  OutlinedButton(onPressed: () => context.go('/local'), child: const Text('Use local AI on this PC')),
                  FilledButton(onPressed: () => context.go('/register'), child: const Text('Get started')),
                  const SizedBox(height: 12),
                  OutlinedButton(onPressed: () => context.go('/login'), child: const Text('I already have an account')),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
