import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;

import 'core/config.dart';
import 'core/platform/desktop.dart';
import 'core/platform/push.dart';
import 'core/platform/updates.dart';
import 'core/providers.dart';
import 'core/storage/secure_store.dart';
import 'core/theme.dart';
import 'features/chat/chat_controller.dart';
import 'features/reminders/reminder_watcher.dart';
import 'router.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final store = FlutterSecureStore();
  final overrides = <Override>[secureStoreProvider.overrideWithValue(store)];
  if (!kIsWeb && (defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS)) {
    final platform = defaultTargetPlatform == TargetPlatform.android ? 'android' : 'ios';
    overrides.add(pushBridgeProvider.overrideWithValue(MethodChannelPushBridge(platform)));
  }
  final desktop = await createDesktopShell(minimizeToTray: await store.read(StoreKeys.minimizeToTray) == 'true');
  if (desktop != null) overrides.add(desktopShellProvider.overrideWithValue(_PersistedTray(desktop, store)));
  runApp(ProviderScope(overrides: overrides, child: const DhanzApp()));
}

/// Remembers the minimize-to-tray choice across restarts.
class _PersistedTray implements DesktopShell {
  _PersistedTray(this._shell, this._store);

  final DesktopShell _shell;
  final SecureStore _store;

  @override
  bool get minimizeToTray => _shell.minimizeToTray;

  @override
  Future<void> setMinimizeToTray(bool value) async {
    await _shell.setMinimizeToTray(value);
    await _store.write(StoreKeys.minimizeToTray, '$value');
  }

  @override
  Future<void> notifyReplyReady({required String conversationId, required String title}) =>
      _shell.notifyReplyReady(conversationId: conversationId, title: title);

  @override
  Future<void> notifyReminder(String text) => _shell.notifyReminder(text);

  @override
  Stream<String> get openedRoutes => _shell.openedRoutes;
}

class DhanzApp extends ConsumerStatefulWidget {
  const DhanzApp({super.key});

  @override
  ConsumerState<DhanzApp> createState() => _DhanzAppState();
}

class _DhanzAppState extends ConsumerState<DhanzApp> {
  final _subs = <StreamSubscription<Object>>[];
  late final AppLifecycleListener _lifecycle;

  @override
  void initState() {
    super.initState();
    // Notification taps (phone push or desktop notification) open the finished conversation.
    _subs.add(ref.read(desktopShellProvider).openedRoutes.listen(_open));
    final push = ref.read(pushBridgeProvider);
    if (push != null) {
      _subs.add(push.notificationTaps.listen(_openNotification));
      unawaited(push.initialNotification().then((data) => data == null ? null : _openNotification(data)));
    }
    // Back from the background: pick up replies that finished while the app was suspended.
    _lifecycle = AppLifecycleListener(onResume: () => unawaited(ref.read(chatControllerProvider.notifier).refresh()));
  }

  void _openNotification(Map<String, String> data) {
    final conversation = data['conversation_id'];
    if (conversation != null) {
      _open('/chat/$conversation');
    } else if (data.containsKey('reminder_id')) {
      _open('/reminders');
    }
  }

  void _open(String location) {
    ref.read(routerProvider).go(location);
    if (location.startsWith('/chat/')) unawaited(ref.read(chatControllerProvider.notifier).refresh());
  }

  @override
  void dispose() {
    for (final s in _subs) {
      unawaited(s.cancel());
    }
    _lifecycle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(pushControllerProvider, (_, _) {}); // keeps push registration alive while signed in
    ref.listen(reminderWatcherProvider, (_, _) {}); // desktop: due reminders as system notifications
    return MaterialApp.router(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: dhanzLightTheme,
      darkTheme: dhanzDarkTheme,
      themeMode: ref.watch(themeModeProvider),
      routerConfig: ref.watch(routerProvider),
      builder: (context, child) => UpdateBanner(child: child ?? const SizedBox.shrink()),
    );
  }
}
