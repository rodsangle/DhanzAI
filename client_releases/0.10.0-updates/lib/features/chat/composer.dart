import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/files.dart';
import '../../core/clipboard_images.dart';
import '../../core/uploads/upload_queue.dart';
import '../../core/uploads/folder_upload_action.dart';
import '../projects/projects_controller.dart';
import '../../models/models.dart';
import 'file_icons.dart';
import '../conversations/conversations_controller.dart';
import 'chat_controller.dart';
import 'draft_spelling.dart';
import '../voice/prompt_microphone.dart';

/// Message input with model picker and send/stop button.
/// Enter sends; Shift+Enter inserts a newline.
class Composer extends ConsumerStatefulWidget {
  const Composer({super.key, required this.onSend, this.onCodex});

  final ValueChanged<String> onSend;
  final ValueChanged<String>? onCodex;

  @override
  ConsumerState<Composer> createState() => _ComposerState();
}

class _ComposerState extends ConsumerState<Composer> {
  final _controller = TextEditingController();
  bool _deviceAutocorrect = true;
  bool _folderBusy = false;
  bool _pasteBusy = false;
  late final void Function() _unbindPaste;

  @override
  void initState() {
    super.initState();
    _unbindPaste = bindClipboardImages(
      active: () => mounted && _focus.hasFocus,
      onImages: (images) => _pasteImages(images),
    );
  }

  Future<void> _pasteImages(List<ClipboardImageSource>? images) async {
    if (_pasteBusy) {
      return;
    }
    setState(() => _pasteBusy = true);
    try {
      final queue = ref.read(uploadQueueProvider.notifier);
      final ticket = queue.ticket();
      final project = ref.read(selectedProjectProvider);
      final target = ref.read(chatControllerProvider.notifier).uploadTarget;
      final sources = images ?? await readClipboardImages();
      validateClipboardImages(sources);
      final files = await Future.wait(
        sources.map(
          (image) async => (name: image.name, bytes: await image.read()),
        ),
      );
      if (files.any(
        (file) => file.bytes.isEmpty || file.bytes.length > 10 * 1024 * 1024,
      )) {
        throw StateError('Clipboard image is empty or exceeds 10 MB.');
      }
      queue.files(files, ticket: ticket, projectId: project, target: target);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _pasteBusy = false);
    }
  }

  late final FocusNode _focus = FocusNode(onKeyEvent: _onKey);

  @override
  void dispose() {
    _unbindPaste();
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent event) {
    if (event is KeyDownEvent &&
        event.logicalKey == LogicalKeyboardKey.enter &&
        !HardwareKeyboard.instance.isShiftPressed) {
      _submit();
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  Future<void> _attach() async {
    final queue = ref.read(uploadQueueProvider.notifier);
    final ticket = queue.ticket();
    final project = ref.read(selectedProjectProvider);
    final target = ref.read(chatControllerProvider.notifier).uploadTarget;
    try {
      final files = await pickFiles();
      queue.files(files, ticket: ticket, projectId: project, target: target);
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    }
  }

  Future<void> _attachFolder() async {
    setState(() => _folderBusy = true);
    final target = ref.read(chatControllerProvider.notifier).uploadTarget;
    try {
      await queueFolderUpload(context, ref, target: target);
    } finally {
      if (mounted) setState(() => _folderBusy = false);
    }
  }

  void _submit() {
    final chat = ref.read(chatControllerProvider);
    var text = _controller.text;
    if (_folderBusy || _pasteBusy || chat.uploading > 0 || chat.loading) {
      return;
    }
    if (text.trim().isEmpty && chat.attachments.isNotEmpty) {
      // Attachments alone: ask for the obvious thing rather than refusing to send.
      text = chat.attachments.every((a) => a.fileType == 'image')
          ? 'Describe this image.'
          : 'Summarize this file.';
    }
    if (text.trim().isEmpty) {
      return;
    }
    _controller.clear();
    widget.onSend(text);
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
        border: Border.all(color: theme.colorScheme.outlineVariant),
      ),
      padding: const EdgeInsets.fromLTRB(8, 4, 8, 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (chat.queuedPrompts.isNotEmpty)
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 130),
              child: SingleChildScrollView(
                child: Column(
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            chat.queuePaused
                                ? 'Queued prompts · paused'
                                : 'Queued · sends after this reply',
                            style: theme.textTheme.labelMedium,
                          ),
                        ),
                        if (chat.queuePaused)
                          TextButton(
                            onPressed: () => ref
                                .read(chatControllerProvider.notifier)
                                .resumeQueue(),
                            child: const Text('Resume'),
                          ),
                      ],
                    ),
                    for (final prompt in chat.queuedPrompts)
                      Row(
                        children: [
                          const Icon(Icons.schedule, size: 16),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              prompt.text,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          if (prompt.attachments.isNotEmpty)
                            Text(' · ${prompt.attachments.length} files'),
                          IconButton(
                            tooltip: 'Remove queued prompt',
                            icon: const Icon(Icons.close, size: 18),
                            onPressed: () => ref
                                .read(chatControllerProvider.notifier)
                                .removeQueuedPrompt(prompt.id),
                          ),
                        ],
                      ),
                  ],
                ),
              ),
            ),
          if (chat.attachments.isNotEmpty || chat.uploading > 0)
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
                        onDeleted: () => ref
                            .read(chatControllerProvider.notifier)
                            .removeAttachment(a.id),
                        deleteButtonTooltipMessage: 'Remove attachment',
                      ),
                    if (chat.uploading > 0)
                      Chip(
                        avatar: const SizedBox.square(
                          dimension: 14,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        label: Text('Uploading ${chat.uploading}…'),
                      ),
                  ],
                ),
              ),
            ),
          TextField(
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
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              icon: Icon(
                _folderBusy
                    ? Icons.hourglass_top
                    : Icons.create_new_folder_outlined,
              ),
              label: Text(_folderBusy ? 'Preparing folder…' : 'Upload folder'),
              onPressed: _folderBusy || _pasteBusy || chat.loading || chat.uploading > 0
                  ? null
                  : _attachFolder,
            ),
          ),
          if (widget.onCodex != null)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                icon: const Icon(Icons.code),
                label: const Text('Continue in Codex'),
                onPressed:
                    _folderBusy ||
                        chat.loading ||
                        chat.streaming ||
                        chat.uploading > 0
                    ? null
                    : () => widget.onCodex!(_controller.text),
              ),
            ),
          Row(
            children: [
              // Pickers take the free space (shrinking the model name if needed); send stays at the right edge.
              Expanded(
                child: Row(
                  children: [
                    DraftSpellingButton(
                      enabled: !chat.loading,
                      controller: _controller,
                      deviceAutocorrect: _deviceAutocorrect,
                      onDeviceAutocorrectChanged: (value) =>
                          setState(() => _deviceAutocorrect = value),
                    ),
                    IconButton(
                      tooltip: 'Paste image',
                      icon: Icon(
                        _pasteBusy ? Icons.hourglass_top : Icons.content_paste,
                      ),
                      onPressed: _pasteBusy ? null : () => _pasteImages(null),
                    ),
                    IconButton(
                      tooltip: 'Attach files',
                      icon: const Icon(Icons.attach_file),
                      onPressed: chat.loading || _folderBusy ? null : _attach,
                    ),
                    PromptMicrophone(
                      compact: true,
                      label: 'Dictate message',
                      enabled: !chat.loading,
                      onTranscript: (text) {
                        final prefix = _controller.text.trimRight();
                        _controller.text =
                            '$prefix${prefix.isEmpty ? '' : ' '}$text';
                        _controller.selection = TextSelection.collapsed(
                          offset: _controller.text.length,
                        );
                      },
                      onError: (text) =>
                          ScaffoldMessenger.of(context)
                              .showSnackBar(SnackBar(content: Text(text))),
                    ),
                    Flexible(child: _ModelPicker(selected: chat.modelKey)),
                    _WebModePicker(mode: chat.webMode),
                  ],
                ),
              ),
              if (chat.streaming)
                IconButton.filledTonal(
                  tooltip: 'Stop generating',
                  icon: const Icon(Icons.stop_rounded),
                  onPressed: () =>
                      ref.read(chatControllerProvider.notifier).stop(),
                ),
              ListenableBuilder(
                listenable: _controller,
                builder: (context, _) => IconButton.filled(
                  tooltip: chat.streaming ? 'Queue prompt' : 'Send',
                  icon: const Icon(Icons.arrow_upward_rounded),
                  onPressed:
                      _folderBusy || _pasteBusy ||
                          (_controller.text.trim().isEmpty &&
                              chat.attachments.isEmpty) ||
                          chat.uploading > 0 ||
                          chat.loading
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
      onSelected: (key) => ref
          .read(chatControllerProvider.notifier)
          .selectModel(key == 'auto' ? null : key),
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
              leading: Icon(
                m.capabilities.contains('local')
                    ? Icons.computer
                    : Icons.cloud_outlined,
              ),
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
                child: Text(
                  current?.displayName ?? 'Auto',
                  overflow: TextOverflow.ellipsis,
                ),
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
    WebMode.auto: (
      'Web: Auto',
      'Search when the question needs current information',
      Icons.travel_explore,
    ),
    WebMode.always: (
      'Web: Always',
      'Search the web for every message',
      Icons.public,
    ),
    WebMode.off: (
      'Web: Off',
      'Answer without searching or reading links',
      Icons.public_off,
    ),
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final available =
        ref.watch(serverInfoProvider).value?.features.webSearch ?? false;
    final (label, _, icon) = _labels[mode]!;
    return PopupMenuButton<WebMode>(
      tooltip: available
          ? 'Web research'
          : 'Web research (search not configured on the server)',
      initialValue: mode,
      onSelected: (m) =>
          ref.read(chatControllerProvider.notifier).setWebMode(m),
      itemBuilder: (context) => [
        for (final e in _labels.entries)
          PopupMenuItem(
            value: e.key,
            child: ListTile(
              leading: Icon(e.value.$3),
              title: Text(e.value.$1),
              subtitle: Text(e.value.$2),
            ),
          ),
        if (!available)
          const PopupMenuItem(
            enabled: false,
            child: Text(
              'Web search isn’t configured on this server. Pasted links can still be read.',
            ),
          ),
      ],
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 18,
              color: mode == WebMode.off
                  ? null
                  : Theme.of(context).colorScheme.primary,
            ),
            // Phones show just the icon to leave room for the model name.
            if (MediaQuery.sizeOf(context).width >= 600) ...[
              const SizedBox(width: 6),
              Text(label),
            ],
          ],
        ),
      ),
    );
  }
}
