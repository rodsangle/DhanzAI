import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/api/api_client.dart';
import '../../core/files.dart';
import '../../core/providers.dart';
import '../../models/models.dart';

class ShowDoneReminders extends Notifier<bool> {
  @override
  bool build() => false;

  void toggle() => state = !state;
}

final showDoneRemindersProvider = NotifierProvider<ShowDoneReminders, bool>(ShowDoneReminders.new);

final remindersProvider = FutureProvider.autoDispose<List<Reminder>>(
  (ref) => ref.watch(apiClientProvider).reminders(includeDone: ref.watch(showDoneRemindersProvider)),
);

/// Reminders set by asking Dhanz ("remind me to …") or added here. Due reminders arrive as notifications.
class RemindersScreen extends ConsumerWidget {
  const RemindersScreen({super.key});

  void _snack(BuildContext context, String text) => ScaffoldMessenger.of(context)
    ..clearSnackBars()
    ..showSnackBar(SnackBar(content: Text(text)));

  Future<void> _run(BuildContext context, WidgetRef ref, Future<void> Function(ApiClient api) action) async {
    try {
      await action(ref.read(apiClientProvider));
      ref.invalidate(remindersProvider);
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  Future<void> _add(BuildContext context, WidgetRef ref) async {
    final result = await showDialog<(String, DateTime)>(context: context, builder: (_) => const _NewReminderDialog());
    if (result == null || !context.mounted) return;
    await _run(context, ref, (api) => api.createReminder(result.$1, result.$2));
  }

  Future<void> _calendar(BuildContext context, WidgetRef ref, Reminder r) async {
    try {
      final bytes = await ref.read(apiClientProvider).reminderCalendarFile(r.id);
      final saved = await saveBytes('dhanz-reminder.ics', bytes, mimeType: 'text/calendar');
      if (saved && context.mounted) _snack(context, 'Saved. Open the file to add it to your calendar.');
    } on ApiException catch (e) {
      if (context.mounted) _snack(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final reminders = ref.watch(remindersProvider);
    final showDone = ref.watch(showDoneRemindersProvider);
    final format = DateFormat.yMMMEd().add_jm();
    final now = DateTime.now();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Reminders'),
        leading: IconButton(tooltip: 'Back', icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/chat')),
        actions: [
          IconButton(
            tooltip: showDone ? 'Hide completed' : 'Show completed',
            icon: Icon(showDone ? Icons.check_box : Icons.check_box_outline_blank),
            onPressed: ref.read(showDoneRemindersProvider.notifier).toggle,
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _add(context, ref),
        icon: const Icon(Icons.alarm_add),
        label: const Text('New reminder'),
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: reminders.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => Center(child: Text('Could not load reminders: $e')),
            data: (list) => list.isEmpty
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.all(32),
                      child: Text(
                        'No reminders yet.\nAsk Dhanz, for example: "Remind me to call the bank tomorrow at 10".',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  )
                : ListView(
                    padding: const EdgeInsets.only(bottom: 96),
                    children: [
                      for (final r in list)
                        ListTile(
                          leading: Checkbox(
                            value: r.done,
                            onChanged: (v) => _run(context, ref, (api) => api.updateReminder(r.id, done: v ?? false)),
                          ),
                          title: Text(
                            r.text,
                            style: r.done ? const TextStyle(decoration: TextDecoration.lineThrough) : null,
                          ),
                          subtitle: Text(
                            [
                              format.format(r.dueAt.toLocal()),
                              if (r.location != null) r.location!,
                              if (!r.done && r.dueAt.isBefore(now)) 'overdue',
                            ].join(' · '),
                          ),
                          trailing: PopupMenuButton<String>(
                            tooltip: 'More',
                            onSelected: (action) => switch (action) {
                              'calendar' => _calendar(context, ref, r),
                              'chat' => context.go('/chat/${r.conversationId}'),
                              _ => _run(context, ref, (api) => api.deleteReminder(r.id)),
                            },
                            itemBuilder: (_) => [
                              const PopupMenuItem(value: 'calendar', child: Text('Add to calendar')),
                              if (r.conversationId != null)
                                const PopupMenuItem(value: 'chat', child: Text('Open the conversation')),
                              const PopupMenuItem(value: 'delete', child: Text('Delete')),
                            ],
                          ),
                        ),
                    ],
                  ),
          ),
        ),
      ),
    );
  }
}

class _NewReminderDialog extends StatefulWidget {
  const _NewReminderDialog();

  @override
  State<_NewReminderDialog> createState() => _NewReminderDialogState();
}

class _NewReminderDialogState extends State<_NewReminderDialog> {
  final _text = TextEditingController();
  late DateTime _when = DateTime.now()
      .add(const Duration(hours: 1))
      .copyWith(second: 0, millisecond: 0, microsecond: 0);

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _pick() async {
    final day = await showDatePicker(
      context: context,
      initialDate: _when,
      firstDate: DateTime.now().subtract(const Duration(days: 1)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
    );
    if (day == null || !mounted) return;
    final time = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(_when));
    if (time == null) return;
    setState(() => _when = DateTime(day.year, day.month, day.day, time.hour, time.minute));
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('New reminder'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _text,
            autofocus: true,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Remind me to…'),
            onChanged: (_) => setState(() {}),
          ),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.schedule),
            title: Text(DateFormat.yMMMEd().add_jm().format(_when)),
            trailing: TextButton(onPressed: _pick, child: const Text('Change')),
          ),
        ],
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
        FilledButton(
          onPressed: _text.text.trim().isEmpty ? null : () => Navigator.pop(context, (_text.text.trim(), _when)),
          child: const Text('Save'),
        ),
      ],
    );
  }
}
