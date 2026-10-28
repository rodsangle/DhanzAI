import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../models/models.dart';

/// Numbered, clickable sources under an answer. Numbers match the [n] markers in the text.
class SourcesView extends StatelessWidget {
  const SourcesView({super.key, required this.citations});

  final List<Citation> citations;

  static final _date = DateFormat.yMMMd();

  Future<void> _open(BuildContext context, Citation c) async {
    final uri = Uri.tryParse(c.url);
    if (uri == null || !(uri.scheme == 'https' || uri.scheme == 'http')) return;
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication) && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not open ${c.url}')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Sources', style: theme.textTheme.labelLarge?.copyWith(color: theme.colorScheme.secondary)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final c in citations)
                Tooltip(
                  message: c.url,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: () => _open(context, c),
                    child: Container(
                      constraints: const BoxConstraints(maxWidth: 280),
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerHigh,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: theme.colorScheme.outlineVariant),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          CircleAvatar(
                            radius: 10,
                            backgroundColor: theme.colorScheme.primary,
                            foregroundColor: theme.colorScheme.onPrimary,
                            child: Text('${c.n}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700)),
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  c.title,
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
                                ),
                                const SizedBox(height: 2),
                                Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(
                                      c.fromLibrary ? Icons.local_library_outlined : Icons.public,
                                      size: 12,
                                      color: theme.colorScheme.onSurfaceVariant,
                                    ),
                                    const SizedBox(width: 4),
                                    Flexible(
                                      child: Text(
                                        [
                                          c.siteName ?? c.host,
                                          if (c.publishedAt != null) _date.format(c.publishedAt!),
                                        ].join(' · '),
                                        style: muted,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
          if (citations.any((c) => c.retrievedAt != null))
            Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                'Retrieved ${_date.format(citations.map((c) => c.retrievedAt).whereType<DateTime>().reduce((a, b) => a.isAfter(b) ? a : b))}',
                style: muted,
              ),
            ),
        ],
      ),
    );
  }
}
