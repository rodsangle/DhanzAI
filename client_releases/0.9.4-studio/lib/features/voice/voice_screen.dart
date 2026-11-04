import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../widgets/dhanz_logo.dart';
import '../chat/chat_controller.dart';
import '../chat/markdown_view.dart';
import '../conversations/conversations_controller.dart';
import 'voice_controller.dart';

/// Talk to Dhanz: tap the mic, speak, and hear the answer. Hands-free mode keeps listening.
///
/// The microphone is only used while this screen is open (no background listening), which keeps
/// within Android and iOS rules for microphone access.
class VoiceScreen extends ConsumerStatefulWidget {
  const VoiceScreen({super.key});

  @override
  ConsumerState<VoiceScreen> createState() => _VoiceScreenState();
}

class _VoiceScreenState extends ConsumerState<VoiceScreen> {
  // Read eagerly: `ref` may not be used inside dispose().
  late final VoiceController _voice;

  @override
  void initState() {
    super.initState();
    _voice = ref.read(voiceControllerProvider.notifier);
  }

  @override
  void dispose() {
    // Leaving the screen always releases the microphone and stops speaking. Deferred one microtask
    // because providers must not change while the widget tree is being finalized.
    unawaited(Future.microtask(_voice.stop));
    super.dispose();
  }

  void _openSettings(VoiceState voice) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => Consumer(
        builder: (context, ref, _) {
          final v = ref.watch(voiceControllerProvider);
          final controller = ref.read(voiceControllerProvider.notifier);
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Voice', style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String?>(
                    initialValue: v.voices.contains(v.voice) ? v.voice : null,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Voice'),
                    items: [
                      const DropdownMenuItem(value: null, child: Text('Device default')),
                      for (final name in v.voices)
                        DropdownMenuItem(value: name, child: Text(name.replaceAll('|', ' · '))),
                    ],
                    onChanged: controller.setVoice,
                  ),
                  const SizedBox(height: 16),
                  Text('Speaking speed: ${(v.rate * 2).toStringAsFixed(1)}×'),
                  Slider(value: v.rate, min: 0.2, max: 1.0, divisions: 16, onChanged: controller.setRate),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final voice = ref.watch(voiceControllerProvider);
    final controller = ref.read(voiceControllerProvider.notifier);
    final sttAvailable = ref.watch(serverInfoProvider).value?.features.speechToText ?? false;
    final listening = voice.phase == VoicePhase.listening;
    // Map -60..0 dBFS to a 0..1 pulse for the mic ring.
    final pulse = listening ? ((voice.level + 60) / 60).clamp(0.0, 1.0) : 0.0;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Voice'),
        leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
        actions: [
          IconButton(tooltip: 'Voice settings', icon: const Icon(Icons.tune), onPressed: () => _openSettings(voice)),
          IconButton(
            tooltip: 'Open this conversation',
            icon: const Icon(Icons.chat_bubble_outline),
            onPressed: () {
              final id = ref.read(chatControllerProvider).conversationId;
              context.go(id == null ? '/chat' : '/chat/$id');
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 640),
            child: ListView(
              padding: const EdgeInsets.all(24),
              children: [
                if (!sttAvailable)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.info_outline),
                      title: const Text('Speech recognition is not configured on this server'),
                      subtitle: const Text(
                        'Ask your administrator to set STT_PROVIDER. You can still type in the chat.',
                      ),
                    ),
                  ),
                const SizedBox(height: 16),
                Center(
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    width: 180,
                    height: 180,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: DhanzColors.gold.withValues(alpha: listening ? 0.35 + 0.65 * pulse : 0.25),
                        width: 4 + 14 * pulse,
                      ),
                    ),
                    alignment: Alignment.center,
                    child: SizedBox.square(
                      dimension: 132,
                      child: FilledButton(
                        style: FilledButton.styleFrom(shape: const CircleBorder(), padding: EdgeInsets.zero),
                        onPressed: sttAvailable || voice.busy ? controller.toggle : null,
                        child: switch (voice.phase) {
                          VoicePhase.idle => const Icon(Icons.mic, size: 56, semanticLabel: 'Start talking'),
                          VoicePhase.listening => const Icon(Icons.stop, size: 56, semanticLabel: 'Done talking'),
                          VoicePhase.transcribing || VoicePhase.thinking => const SizedBox.square(
                            dimension: 44,
                            child: CircularProgressIndicator(strokeWidth: 4),
                          ),
                          VoicePhase.speaking => const Icon(Icons.volume_off, size: 56, semanticLabel: 'Stop'),
                        },
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  voice.status ?? (voice.phase == VoicePhase.idle ? 'Tap the microphone and speak' : ''),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.titleMedium,
                ),
                if (voice.error != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    voice.error!,
                    textAlign: TextAlign.center,
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                ],
                const SizedBox(height: 16),
                SwitchListTile(
                  title: const Text('Hands-free conversation'),
                  subtitle: const Text('Listen again after each answer. Works while this screen is open.'),
                  value: voice.handsFree,
                  onChanged: controller.setHandsFree,
                ),
                SwitchListTile(
                  title: const Text('Require “Hey Dhanz”'),
                  subtitle: const Text('Only respond to requests that start with the wake phrase.'),
                  value: voice.wakePhrase,
                  onChanged: controller.setWakePhrase,
                ),
                if (voice.transcript != null) ...[
                  const Divider(height: 32),
                  Text('You said', style: theme.textTheme.labelLarge?.copyWith(color: theme.colorScheme.secondary)),
                  const SizedBox(height: 4),
                  Text(voice.transcript!, style: theme.textTheme.bodyLarge),
                ],
                if (voice.reply != null) ...[
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      const DhanzLogo(size: 22),
                      const SizedBox(width: 8),
                      Text('Dhanz', style: theme.textTheme.labelLarge?.copyWith(color: theme.colorScheme.secondary)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  MarkdownView(voice.reply!),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
