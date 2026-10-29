import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:local_notifier/local_notifier.dart';
import 'package:tray_manager/tray_manager.dart';
import 'package:window_manager/window_manager.dart';

import 'desktop.dart';

Future<DesktopShell?> createDesktopShell({required bool minimizeToTray}) async {
  if (!(Platform.isWindows || Platform.isMacOS || Platform.isLinux)) return null;
  try {
    final shell = _NativeDesktopShell(minimizeToTray);
    await shell._init();
    return shell;
  } on Object catch (e) {
    // A missing tray (some Linux desktops) must not stop the app from starting.
    debugPrint('Desktop integration unavailable: $e');
    return null;
  }
}

class _NativeDesktopShell with WindowListener, TrayListener implements DesktopShell {
  _NativeDesktopShell(this._minimizeToTray);

  bool _minimizeToTray;
  bool _hasTray = false;
  final _opened = StreamController<String>.broadcast();

  Future<void> _init() async {
    await windowManager.ensureInitialized();
    windowManager.addListener(this);
    await windowManager.setPreventClose(true);
    await localNotifier.setup(appName: 'DHANZ AI', shortcutPolicy: ShortcutPolicy.requireCreate);
    try {
      await trayManager.setIcon(Platform.isWindows ? 'assets/tray/tray_icon.ico' : 'assets/tray/tray_icon.png');
      if (!Platform.isLinux) await trayManager.setToolTip('DHANZ AI');
      await trayManager.setContextMenu(
        Menu(
          items: [
            MenuItem(key: 'show', label: 'Open DHANZ AI'),
            MenuItem.separator(),
            MenuItem(key: 'quit', label: 'Quit DHANZ AI'),
          ],
        ),
      );
      trayManager.addListener(this);
      _hasTray = true;
    } on Object catch (e) {
      // No system tray (e.g. GNOME without AppIndicator): closing the window quits as usual.
      debugPrint('System tray unavailable: $e');
    }
  }

  @override
  bool get minimizeToTray => _minimizeToTray && _hasTray;

  @override
  Future<void> setMinimizeToTray(bool value) async => _minimizeToTray = value;

  @override
  Stream<String> get openedConversations => _opened.stream;

  Future<void> _showWindow() async {
    await windowManager.show();
    await windowManager.focus();
  }

  Future<void> _quit() async {
    if (_hasTray) await trayManager.destroy();
    await windowManager.setPreventClose(false);
    await windowManager.destroy();
  }

  @override
  Future<void> notifyReplyReady({required String conversationId, required String title}) async {
    if (await windowManager.isVisible() && await windowManager.isFocused()) return;
    final notification = LocalNotification(title: 'Dhanz finished your answer', body: title);
    notification.onClick = () {
      unawaited(_showWindow());
      _opened.add(conversationId);
    };
    await notification.show();
  }

  @override
  void onWindowClose() => unawaited(minimizeToTray ? windowManager.hide() : _quit());

  @override
  void onTrayIconMouseDown() => unawaited(_showWindow());

  @override
  void onTrayIconRightMouseDown() => unawaited(trayManager.popUpContextMenu());

  @override
  void onTrayMenuItemClick(MenuItem menuItem) {
    switch (menuItem.key) {
      case 'show':
        unawaited(_showWindow());
      case 'quit':
        unawaited(_quit());
    }
  }
}
