import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'desktop_stub.dart' if (dart.library.io) 'desktop_io.dart' as impl;

/// Windows/macOS/Linux integration: tray icon, minimize to tray, and notifications when an answer
/// finishes while the window is in the background.
abstract class DesktopShell {
  bool get minimizeToTray;
  Future<void> setMinimizeToTray(bool value);

  /// Shows a system notification unless the window is focused. Clicking it opens [conversationId].
  Future<void> notifyReplyReady({required String conversationId, required String title});

  /// Shows a reminder that is due (always, even when the window is focused).
  Future<void> notifyReminder(String text);

  /// App locations (e.g. `/chat/<id>`, `/reminders`) opened by clicking a notification.
  Stream<String> get openedRoutes;
}

/// Phones, the web and tests.
class NoDesktopShell implements DesktopShell {
  @override
  bool get minimizeToTray => false;

  @override
  Future<void> setMinimizeToTray(bool value) async {}

  @override
  Future<void> notifyReplyReady({required String conversationId, required String title}) async {}

  @override
  Future<void> notifyReminder(String text) async {}

  @override
  Stream<String> get openedRoutes => const Stream.empty();
}

/// Sets up the desktop shell when running on a desktop OS; returns null elsewhere.
Future<DesktopShell?> createDesktopShell({required bool minimizeToTray}) =>
    impl.createDesktopShell(minimizeToTray: minimizeToTray);

/// `main()` overrides this with the real shell on desktop.
final desktopShellProvider = Provider<DesktopShell>((ref) => NoDesktopShell());

/// Bumped to re-render settings after the tray preference changes.
final minimizeToTrayProvider = NotifierProvider<MinimizeToTray, bool>(MinimizeToTray.new);

class MinimizeToTray extends Notifier<bool> {
  @override
  bool build() => ref.watch(desktopShellProvider).minimizeToTray;

  Future<void> set(bool value) async {
    await ref.read(desktopShellProvider).setMinimizeToTray(value);
    state = value;
  }
}
