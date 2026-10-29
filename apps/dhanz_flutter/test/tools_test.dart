import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/app_version.dart';
import 'package:dhanz_ai/core/platform/desktop.dart';
import 'package:dhanz_ai/core/platform/updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/features/reminders/reminder_watcher.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:dhanz_ai/router.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';

import 'fake_backend.dart';

class RecordingDesktop implements DesktopShell {
  final reminders = <String>[];

  @override
  bool get minimizeToTray => false;

  @override
  Future<void> setMinimizeToTray(bool value) async {}

  @override
  Future<void> notifyReplyReady({required String conversationId, required String title}) async {}

  @override
  Future<void> notifyReminder(String text) async => reminders.add(text);

  @override
  Stream<String> get openedRoutes => const Stream.empty();
}

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;

  List<Override> overrides({DesktopShell? desktop}) => [
    secureStoreProvider.overrideWithValue(store),
    apiClientProvider.overrideWith(
      (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
    ),
    appVersionProvider.overrideWith((ref) async => '0.6.0'),
    updatePlatformProvider.overrideWithValue(null),
    if (desktop != null) desktopShellProvider.overrideWithValue(desktop),
  ];

  setUp(() async {
    backend = FakeBackend();
    store = MemorySecureStore();
    await ApiClient(
      store: store,
      baseUrl: 'http://test',
      clientFactory: backend.client,
    ).register('ada@example.com', 'correct-horse-9', 'Ada');
  });

  final soon = DateTime.now().toUtc().add(const Duration(days: 1)).toIso8601String();
  Map<String, dynamic> reminderActivity(String id) => {
    'tool': 'create_reminder',
    'summary': 'Reminder set: Call the bank',
    'error': false,
    'action': {'type': 'reminder', 'id': id, 'text': 'Call the bank', 'due_at': soon, 'location': null},
  };
  const emailActivity = {
    'tool': 'draft_email',
    'summary': 'Email draft: Lunch',
    'error': false,
    'action': {
      'type': 'email',
      'to': 'bob@example.com',
      'subject': 'Lunch',
      'body': 'Noon?',
      'mailto': 'mailto:bob@example.com?subject=Lunch&body=Noon%3F',
    },
  };

  test('client time carries the UTC offset', () {
    expect(clientTimeNow(DateTime(2026, 10, 29, 14, 5, 7, 123)), matches(r'^2026-10-29T14:05:07[+-]\d\d:\d\d$'));
  });

  test('messages carry the device time, and tool activity lands on the reply', () async {
    final c = ProviderContainer(overrides: overrides());
    addTearDown(c.dispose);
    await c.read(authControllerProvider.future);
    backend.toolActivity = [
      {'tool': 'calculate', 'summary': '12*7 = 84', 'error': false, 'action': null},
      reminderActivity('r1'),
    ];
    await c.read(chatControllerProvider.notifier).send('12*7, and remind me to call the bank tomorrow');
    expect(backend.chatBodies.single['client_time'], matches(r'[+-]\d\d:\d\d$'));
    final reply = c.read(chatControllerProvider).messages.last;
    expect(reply.toolActivity.map((a) => a.summary), ['12*7 = 84', 'Reminder set: Call the bank']);
    expect(reply.toolActivity.last.action!['type'], 'reminder');
  });

  testWidgets('reminder and email cards offer their actions', (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    backend.reminders.add({
      'id': 'r1',
      'text': 'Call the bank',
      'due_at': soon,
      'duration_minutes': null,
      'location': null,
      'conversation_id': null,
      'notified_at': null,
      'done_at': null,
      'created_at': soon,
    });
    backend.toolActivity = [
      {'tool': 'calculate', 'summary': '12*7 = 84', 'error': false, 'action': null},
      reminderActivity('r1'),
      emailActivity,
    ];
    await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextField, 'Message Dhanz…'), 'Do the things');
    await tester.pump();
    await tester.tap(find.byTooltip('Send'));
    await tester.pumpAndSettle();

    expect(find.text('12*7 = 84'), findsOneWidget);
    expect(find.text('Call the bank'), findsOneWidget);
    expect(find.text('Add to calendar'), findsOneWidget);
    expect(find.text('Lunch'), findsOneWidget);
    expect(find.text('To bob@example.com · not sent yet'), findsOneWidget);
    expect(find.text('Open in email app'), findsOneWidget);

    await tester.tap(find.text('All reminders'));
    await tester.pumpAndSettle();
    expect(find.text('Reminders'), findsOneWidget);
    expect(find.text('Call the bank'), findsOneWidget);
  });

  testWidgets('reminders screen: add, complete and delete', (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(ProviderScope(overrides: overrides(), child: const DhanzApp()));
    await tester.pumpAndSettle();
    final container = ProviderScope.containerOf(tester.element(find.byType(Scaffold).first));
    container.read(routerProvider).go('/reminders');
    await tester.pumpAndSettle();
    expect(find.textContaining('No reminders yet'), findsOneWidget);

    await tester.tap(find.text('New reminder'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, 'Water the plants');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilledButton, 'Save'));
    await tester.pumpAndSettle();
    expect(backend.reminders.single['text'], 'Water the plants');
    expect(backend.reminders.single['due_at'] as String, matches(r'[+-]\d\d:\d\d$'));
    expect(find.text('Water the plants'), findsOneWidget);

    await tester.tap(find.byType(Checkbox));
    await tester.pumpAndSettle();
    expect(backend.reminders.single['done_at'], isNotNull);
    expect(find.text('Water the plants'), findsNothing); // completed ones are hidden by default

    await tester.tap(find.byTooltip('Show completed'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('More'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(backend.reminders, isEmpty);
  });

  test('desktop: due reminders become system notifications, once', () async {
    final desktop = RecordingDesktop();
    final c = ProviderContainer(overrides: overrides(desktop: desktop));
    addTearDown(c.dispose);
    await c.read(authControllerProvider.future);
    String at(Duration d) => DateTime.now().toUtc().add(d).toIso8601String();
    for (final (id, text, due) in [
      ('a', 'Due now', at(const Duration(minutes: -1))),
      ('b', 'Long overdue', at(const Duration(hours: -3))),
      ('c', 'Later', at(const Duration(hours: 2))),
    ]) {
      backend.reminders.add({
        'id': id,
        'text': text,
        'due_at': due,
        'duration_minutes': null,
        'location': null,
        'conversation_id': null,
        'notified_at': null,
        'done_at': null,
        'created_at': due,
      });
    }
    c.listen(reminderWatcherProvider, (_, _) {});
    final watcher = c.read(reminderWatcherProvider.notifier);
    await watcher.check();
    await watcher.check();
    expect(desktop.reminders, ['Due now']);
  });
}
