import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/files.dart';
import '../../models/models.dart';
import 'file_icons.dart';
import '../conversations/conversations_controller.dart';
import 'chat_controller.dart';
import 'draft_spelling.dart';

/// Message input with model picker and send/stop button.
/// Enter sends; Shift+Enter inserts a newline.
class Composer extends ConsumerStatefulWidget {
  const Composer({super.key, required this.onSend});

  final Future<String?> Function(String text, VoidCallback onSubmitted) onSend;

  @override
  ConsumerState<Composer> createState() => _ComposerState();
}

class _ComposerState extends ConsumerState<Composer> {
  final _controller = TextEditingController();
  bool _deviceAutocorrect = true;
  int _submitVersion = 0;
  late final FocusNode _focus = FocusNode(onKeyEvent: _onKey);

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is KeyDownEvent &&
        event.logicalKey == LogicalKeyboardKey.enter &&
        !HardwareKeyboard.instance.isShiftPressed) {
      unawaited(_submit());
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  Future<void> _attach() async {
    final chat = ref.read(chatControllerProvider.notifier);
    await chat.attachFiles(pickFiles);
  }

  Future<void> _submit() async {
    final chat = ref.read(chatControllerProvider);
    var text = _controller.text;
    if (chat.streaming || chat.sending) return;
    final version = ++_submitVersion;
    if (text.trim().isEmpty && (chat.attachments.isNotEmpty || chat.uploading > 0)) {
      // Without an instruction, ask for intent rather than silently choosing a summary.
      text = 'Read the attached files and ask what I would like you to do with them.';
    }
    if (text.trim().isEmpty) return;
    final draft = _controller.text;
    final id = await widget.onSend(text, () {
      if (mounted && version == _submitVersion && _controller.text == draft) _controller.clear();
    });
    if (!mounted || version != _submitVersion) return;
    if (id == null && _controller.text.isEmpty) _controller.text = draft;
    _focus.requestFocus();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final chat = ref.watch(chatControllerProvider);
    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(22),
        // A faint accent edge, as in the theme concepts; the text field inside shows focus.
        border: Border.all(
          color: Color.alphaBlend(theme.colorScheme.primary.withValues(alpha: 0.3), theme.colorScheme.outlineVariant),
        ),
      ),
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (chat.attachments.isNotEmpty || chat.uploading > 0 || chat.failedAttachments.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(4, 6, 4, 0),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    for (final a in chat.attachments)
                      InputChip(
                        avatar: Icon(fileIcon(a.fileType), size: 18),
                        label: Text(a.title, overflow: TextOverflow.ellipsis),
                        tooltip: a.notes ?? a.title,
                        onDeleted: chat.sending
                            ? null
                            : () => ref.read(chatControllerProvider.notifier).removeAttachment(a.id),
                        deleteButtonTooltipMessage: 'Remove attachment',
                      ),
                    for (final name in chat.failedAttachments)
                      InputChip(
                        avatar: Icon(Icons.error_outline, color: theme.colorScheme.error, size: 18),
                        label: Text('$name — upload failed'),
                        onDeleted: chat.sending
                            ? null
                            : () => ref.read(chatControllerProvider.notifier).removeFailedAttachment(name),
                        deleteButtonTooltipMessage: 'Remove failed attachment',
                      ),
                    if (chat.uploading > 0)
                      Chip(
                        avatar: const SizedBox.square(dimension: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                        label: const Text('Uploading and reading files…'),
                      ),
                  ],
                ),
              ),
            ),
          TextField(
            readOnly: chat.sending,
            controller: _controller,
            autocorrect: _deviceAutocorrect,
            enableSuggestions: _deviceAutocorrect,
            focusNode: _focus,
            minLines: 1,
            maxLines: 8,
            textInputAction: TextInputAction.newline,
            decoration: const InputDecoration(
              hintText: 'Message Dhanz…',
              filled: false,
              border: InputBorder.none,
              focusedBorder: InputBorder.none,
            ),
          ),
          if (chat.sending)
            Semantics(
              liveRegion: true,
              child: Padding(
                padding: EdgeInsets.all(8),
                child: Text('Your message is queued. Waiting for attachments to be ready…'),
              ),
            ),
          Row(
            children: [
              // Pickers take the free space (shrinking the model name if needed); send stays at the right edge.
              Expanded(
                child: Row(
                  children: [
                    DraftSpellingButton(
                      enabled: !chat.sending,
                      controller: _controller,
                      deviceAutocorrect: _deviceAutocorrect,
                      onDeviceAutocorrectChanged: (value) => setState(() => _deviceAutocorrect = value),
                    ),
                    IconButton(
                      tooltip: 'Attach files',
                      icon: const Icon(Icons.attach_file),
                      onPressed: chat.streaming || chat.sending ? null : _attach,
                    ),
                    Flexible(
                      child: IgnorePointer(
                        ignoring: chat.sending,
                        child: _ModelPicker(selected: chat.modelKey),
                      ),
                    ),
                    IgnorePointer(
                      ignoring: chat.sending,
                      child: _WebModePicker(mode: chat.webMode),
                    ),
                  ],
                ),
              ),
              if (chat.sending)
                IconButton.filledTonal(
                  tooltip: 'Cancel pending send',
                  icon: const Icon(Icons.close),
                  onPressed: () {
                    _submitVersion++;
                    ref.read(chatControllerProvider.notifier).cancelPendingSend();
                  },
                )
              else if (chat.streaming)
                IconButton.filledTonal(
                  tooltip: 'Stop generating',
                  icon: const Icon(Icons.stop_rounded),
                  onPressed: () => ref.read(chatControllerProvider.notifier).stop(),
                )
              else
                ListenableBuilder(
                  listenable: _controller,
                  builder: (context, _) => IconButton.filled(
                    tooltip: 'Send',
                    icon: const Icon(Icons.arrow_upward_rounded),
                    onPressed: (_controller.text.trim().isEmpty && chat.attachments.isEmpty && chat.uploading == 0)
                        ? null
                        : _submit,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ModelPicker extends ConsumerWidget {
  const _ModelPicker({required this.selected});

  final String? selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final models = ref.watch(modelsProvider).value ?? const <AiModel>[];
    final current = models.where((m) => m.key == selected).firstOrNull;
    return PopupMenuButton<String>(
      tooltip: 'Choose AI model',
      initialValue: selected ?? 'auto',
      onSelected: (key) => ref.read(chatControllerProvider.notifier).selectModel(key == 'auto' ? null : key),
      itemBuilder: (context) => [
        const PopupMenuItem(
          value: 'auto',
          child: ListTile(
            leading: Icon(Icons.auto_awesome),
            title: Text('Auto'),
            subtitle: Text('Dhanz picks the best model for each message'),
          ),
        ),
        for (final m in models)
          PopupMenuItem(
            value: m.key,
            child: ListTile(
              leading: Icon(m.capabilities.contains('local') ? Icons.computer : Icons.cloud_outlined),
              title: Text(m.displayName),
              subtitle: Text(m.provider),
            ),
          ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(current == null ? Icons.auto_awesome : Icons.memory, size: 18),
            const SizedBox(width: 6),
            Flexible(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 180),
                child: Text(current?.displayName ?? 'Auto', overflow: TextOverflow.ellipsis),
              ),
            ),
            const Icon(Icons.arrow_drop_down),
          ],
        ),
      ),
    );
  }
}

class _WebModePicker extends ConsumerWidget {
  const _WebModePicker({required this.mode});

  final WebMode mode;

  static const _labels = {
    WebMode.auto: ('Web: Auto', 'Search when the question needs current information', Icons.travel_explore),
    WebMode.always: ('Web: Always', 'Search the web for every message', Icons.public),
    WebMode.off: ('Web: Off', 'Answer without searching or reading links', Icons.public_off),
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final available = ref.watch(serverInfoProvider).value?.features.webSearch ?? false;
    final (label, _, icon) = _labels[mode]!;
    return PopupMenuButton<WebMode>(
      tooltip: available ? 'Web research' : 'Web research (search not configured on the server)',
      initialValue: mode,
      onSelected: (m) => ref.read(chatControllerProvider.notifier).setWebMode(m),
      itemBuilder: (context) => [
        for (final e in _labels.entries)
          PopupMenuItem(
            value: e.key,
            child: ListTile(leading: Icon(e.value.$3), title: Text(e.value.$1), subtitle: Text(e.value.$2)),
          ),
        if (!available)
          const PopupMenuItem(
            enabled: false,
            child: Text('Web search isn’t configured on this server. Pasted links can still be read.'),
          ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 18, color: mode == WebMode.off ? null : Theme.of(context).colorScheme.primary),
            // Phones show just the icon to leave room for the model name.
            if (MediaQuery.sizeOf(context).width >= 600) ...[const SizedBox(width: 6), Text(label)],
          ],
        ),
      ),
    );
  }
}
