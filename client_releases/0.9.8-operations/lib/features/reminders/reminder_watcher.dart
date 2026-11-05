import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_client.dart';
import '../../core/platform/desktop.dart';
import '../../core/providers.dart';
import '../auth/auth_controller.dart';

/// Desktop has no push notifications: while the app runs (also minimised to the tray) it checks for
/// due reminders and shows them as system notifications. Phones get them as push notifications.
class ReminderWatcher extends Notifier<void> {
  static Duration interval = const Duration(minutes: 1);

  /// Reminders older than this when first seen are not announced (e.g. after the PC was off for a day).
  static const lateLimit = Duration(minutes: 15);

  Timer? _timer;
  final _announced = <String>{};

  @override
  void build() {
    final signedIn = ref.watch(authControllerProvider.select((s) => s.value?.id)) != null;
    final shell = ref.watch(desktopShellProvider);
    ref.onDispose(() => _timer?.cancel());
    if (!signedIn || shell is NoDesktopShell) return;
    _timer = Timer.periodic(interval, (_) => unawaited(check()));
    unawaited(check());
  }

  Future<void> check() async {
    try {
      final now = DateTime.now();
      final reminders = await ref.read(apiClientProvider).reminders();
      for (final r in reminders) {
        if (r.dueAt.isAfter(now) || now.difference(r.dueAt) > lateLimit || !_announced.add(r.id)) continue;
        await ref.read(desktopShellProvider).notifyReminder(r.text);
      }
    } on ApiException {
      // offline or signed out: try again next time
    }
  }
}

final reminderWatcherProvider = NotifierProvider<ReminderWatcher, void>(ReminderWatcher.new);
