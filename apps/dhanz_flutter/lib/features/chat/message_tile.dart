import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/models.dart';
import '../../widgets/dhanz_logo.dart';
import 'markdown_view.dart';
import 'sources_view.dart';

class MessageTile extends StatelessWidget {
  const MessageTile({
    super.key,
    required this.message,
    required this.isLast,
    required this.busy,
    required this.onRegenerate,
    required this.onEdit,
    this.researchStatus,
  });

  final ChatMessage message;
  final bool isLast;
  final bool busy;
  final VoidCallback onRegenerate;
  final ValueChanged<ChatMessage> onEdit;

  /// Live research progress shown before the reply text arrives.
  final String? researchStatus;

  Future<void> _copy(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: message.content));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Copied to clipboard')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return message.isUser ? _user(context) : _assistant(context);
  }

  Widget _user(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: Alignment.centerRight,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(
                color: theme.colorScheme.surfaceContainerHighest,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(18),
                  topRight: Radius.circular(18),
                  bottomLeft: Radius.circular(18),
                  bottomRight: Radius.circular(4),
                ),
              ),
              child: SelectableText(message.content, style: theme.textTheme.bodyLarge?.copyWith(height: 1.45)),
            ),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _ActionIcon(icon: Icons.copy_rounded, tooltip: 'Copy', onPressed: () => _copy(context)),
                if (!busy && !message.id.startsWith('pending'))
                  _ActionIcon(icon: Icons.edit_outlined, tooltip: 'Edit and resend', onPressed: () => onEdit(message)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _assistant(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final streaming = message.status == MessageStatus.streaming;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(padding: EdgeInsets.only(top: 2), child: DhanzLogo(size: 30)),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (message.content.isEmpty && streaming)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: researchStatus == null
                      ? const _TypingDots()
                      : Row(
                          children: [
                            const SizedBox.square(dimension: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                            const SizedBox(width: 10),
                            Flexible(child: Text(researchStatus!, style: muted?.copyWith(fontSize: 13))),
                          ],
                        ),
                )
              else if (message.content.isNotEmpty)
                MarkdownView(message.content),
              if (message.citations.isNotEmpty) SourcesView(citations: message.citations),
              if (message.status == MessageStatus.error)
                Container(
                  margin: const EdgeInsets.only(top: 6),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.error.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.error_outline, color: theme.colorScheme.error, size: 20),
                      const SizedBox(width: 8),
                      Expanded(child: Text(message.error ?? 'This reply failed.')),
                    ],
                  ),
                ),
              if (message.status == MessageStatus.stopped)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text('Stopped', style: muted),
                ),
              if (!streaming)
                Row(
                  children: [
                    if (message.content.isNotEmpty)
                      _ActionIcon(icon: Icons.copy_rounded, tooltip: 'Copy', onPressed: () => _copy(context)),
                    if (isLast && !busy)
                      _ActionIcon(icon: Icons.refresh_rounded, tooltip: 'Regenerate', onPressed: onRegenerate),
                    if (message.model != null) ...[
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(message.model!, style: muted, overflow: TextOverflow.ellipsis),
                      ),
                    ],
                  ],
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ActionIcon extends StatelessWidget {
  const _ActionIcon({required this.icon, required this.tooltip, required this.onPressed});

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: tooltip,
    icon: Icon(icon),
    iconSize: 18,
    visualDensity: VisualDensity.compact,
    color: Theme.of(context).colorScheme.onSurfaceVariant,
    onPressed: onPressed,
  );
}

class _TypingDots extends StatefulWidget {
  const _TypingDots();

  @override
  State<_TypingDots> createState() => _TypingDotsState();
}

class _TypingDotsState extends State<_TypingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Semantics(
      label: 'Dhanz is thinking',
      child: AnimatedBuilder(
        animation: _c,
        builder: (context, _) => Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (var i = 0; i < 3; i++)
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color.withValues(alpha: 0.3 + 0.7 * (((_c.value * 3 - i) % 3) < 1 ? 1 : 0)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
