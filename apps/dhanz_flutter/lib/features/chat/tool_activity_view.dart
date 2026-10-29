import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import '../../core/providers.dart';
import '../../models/models.dart';

const _toolIcons = {
  'calculate': Icons.calculate_outlined,
  'convert_units': Icons.straighten,
  'world_time': Icons.public,
  'date_difference': Icons.date_range,
  'date_add': Icons.event,
  'create_reminder': Icons.alarm_add,
  'list_reminders': Icons.alarm,
  'cancel_reminder': Icons.alarm_off,
  'draft_email': Icons.mail_outline,
};

/// What Dhanz's tools did for a reply: small result chips, plus cards for reminders and email drafts.
class ToolActivityView extends ConsumerWidget {
  const ToolActivityView({required this.activity, super.key});

  final List<ToolActivity> activity;

  void _snack(BuildContext context, String text) => ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(SnackBar(content: Text(text)));

  Future<void> _addToCalendar(BuildContext context, WidgetRef ref, String id) async {
    try {
      final bytes = await ref.read(apiClientProvider).reminderCalendarFile(id);
      final saved = await saveBytes('dhanz-reminder.ics', bytes, mimeType: 'text/calendar');
      if (saved && context.mounted) _snack(context, 'Saved. Open the file to add it to your calendar.');
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  Future<void> _openEmail(BuildContext context, Map<String, dynamic> action) async {
    final ok = await launchUrl(Uri.parse(action['mailto'] as String), mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) _snack(context, 'No email app found. Copy the text instead.');
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final chips = activity.where((a) => a.action == null).toList();
    final cards = activity.where((a) => a.action != null).toList();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (chips.isNotEmpty)
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                for (final a in chips)
                  Chip(
                    visualDensity: VisualDensity.compact,
                    avatar: Icon(
                      a.error ? Icons.error_outline : _toolIcons[a.tool] ?? Icons.build_outlined,
                      size: 16,
                      color: a.error ? theme.colorScheme.error : null,
                    ),
                    label: Text(a.summary, style: theme.textTheme.bodySmall),
                  ),
              ],
            ),
          for (final a in cards) ...[
            const SizedBox(height: 8),
            if (a.action!['type'] == 'reminder') _reminderCard(context, ref, a.action!),
            if (a.action!['type'] == 'email') _emailCard(context, a.action!),
          ],
        ],
      ),
    );
  }

  Widget _reminderCard(BuildContext context, WidgetRef ref, Map<String, dynamic> action) {
    final due = DateTime.parse(action['due_at'] as String).toLocal();
    final when = DateFormat.yMMMEd().add_jm().format(due);
    final location = action['location'] as String?;
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.alarm),
              title: Text(action['text'] as String),
              subtitle: Text(location == null ? when : '$when · $location'),
            ),
            Wrap(
              spacing: 8,
              children: [
                TextButton.icon(
                  onPressed: () => _addToCalendar(context, ref, action['id'] as String),
                  icon: const Icon(Icons.event_available, size: 18),
                  label: const Text('Add to calendar'),
                ),
                TextButton.icon(
                  onPressed: () => context.go('/reminders'),
                  icon: const Icon(Icons.list_alt, size: 18),
                  label: const Text('All reminders'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _emailCard(BuildContext context, Map<String, dynamic> action) {
    final to = action['to'] as String? ?? '';
    final subject = action['subject'] as String? ?? '';
    final body = action['body'] as String? ?? '';
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 8, 8, 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.mail_outline),
              title: Text(subject.isEmpty ? 'Email draft' : subject),
              subtitle: Text(to.isEmpty ? 'Not sent: review it in your email app' : 'To $to · not sent yet'),
            ),
            Wrap(
              spacing: 8,
              children: [
                FilledButton.tonalIcon(
                  onPressed: () => _openEmail(context, action),
                  icon: const Icon(Icons.open_in_new, size: 18),
                  label: const Text('Open in email app'),
                ),
                TextButton.icon(
                  onPressed: () async {
                    await Clipboard.setData(ClipboardData(text: subject.isEmpty ? body : 'Subject: $subject\n\n$body'));
                    if (context.mounted) _snack(context, 'Email copied');
                  },
                  icon: const Icon(Icons.copy, size: 18),
                  label: const Text('Copy'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
