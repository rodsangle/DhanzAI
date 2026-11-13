import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/storage/secure_store.dart';
import '../../widgets/text_prompt_dialog.dart';
import '../conversations/conversations_controller.dart';

/// An on-demand daily briefing for a city chosen by the user.
class DailyNewsButton extends ConsumerStatefulWidget {
  const DailyNewsButton({required this.onSend, this.enabled = true, super.key});
  final Future<void> Function(String) onSend;
  final bool enabled;

  @override
  ConsumerState<DailyNewsButton> createState() => _DailyNewsButtonState();
}

class _DailyNewsButtonState extends ConsumerState<DailyNewsButton> {
  bool _busy = false;

  Future<void> _open() async {
    setState(() => _busy = true);
    try {
      final store = ref.read(secureStoreProvider);
      final saved = await store.read(StoreKeys.newsLocation);
      if (!mounted) return;
      final location = await showTextPrompt(
        context,
        title: 'Daily local news',
        confirmLabel: 'Get today’s news',
        label: 'City or area, state and country',
        hint: 'For example: Orlando, Florida, USA',
        initialText: saved ?? '',
        maxLength: 120,
        message: const Text(
          'Choose your area for a current news briefing with source links. '
          'This location is remembered on this device and sent with your news request.',
        ),
      );
      if (location == null || location.trim().isEmpty || !mounted) return;
      final info = await ref.read(serverInfoProvider.future);
      if (!mounted) return;
      if (!info.features.webSearch) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Live web search must be enabled on your server to get current local news.')),
        );
        return;
      }
      final area = location.trim();
      await store.write(StoreKeys.newsLocation, area);
      if (!mounted) return;
      final today = DateTime.now().toIso8601String().substring(0, 10);
      await widget.onSend(
        'Give me my daily local news briefing for $area for today, $today '
        '(my device’s local date). Search the live web for reporting published in the last 24 hours. '
        'Summarize up to five relevant local headlines, explain why each matters, '
        'and include publication dates and clickable source citations. Prefer local outlets and official sources. '
        'Distinguish publication dates from event dates. If no recent reporting is available, say so; '
        'clearly label older coverage and never invent current headlines.',
      );
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not load daily news. Check your server connection and try again.')),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => TextButton.icon(
    onPressed: widget.enabled && !_busy ? _open : null,
    icon: const Icon(Icons.newspaper_outlined),
    label: const Text('Daily local news'),
  );
}
