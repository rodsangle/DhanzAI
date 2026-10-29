import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/auth_controller.dart';
import '../../features/conversations/conversations_controller.dart';
import '../api/api_client.dart';
import '../providers.dart';
import '../storage/secure_store.dart';
import 'app_version.dart';

/// Push notifications on Android (Firebase Cloud Messaging) and iOS (APNs).
///
/// The native code lives in `android/app/src/main/kotlin/.../MainActivity.kt` and
/// `ios/Runner/AppDelegate.swift` and talks to Dart over the `ai.dhanz/push` channel:
///   Dart → native: `requestPermission` → bool, `getToken` → String?, `initialNotification` → Map?
///   native → Dart: `onToken(String)`, `onNotificationTap({"conversation_id"?: ..., "reminder_id"?: ...})`
abstract class PushBridge {
  /// "android" or "ios", as the server expects.
  String get platform;
  Future<bool> requestPermission();

  /// The device token, or null when push is not available (no Firebase config, simulator, …).
  Future<String?> getToken();
  Stream<String> get tokenRefreshes;

  /// Data of notifications the user tapped (conversation_id or reminder_id).
  Stream<Map<String, String>> get notificationTaps;

  /// The data of the notification that launched the app, if any.
  Future<Map<String, String>?> initialNotification();
}

Map<String, String> _stringMap(Object? raw) => {
  for (final e in (raw as Map<Object?, Object?>? ?? const {}).entries)
    if (e.key is String && e.value is String) e.key! as String: e.value! as String,
};

class MethodChannelPushBridge implements PushBridge {
  MethodChannelPushBridge(this.platform) {
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'onToken':
          if (call.arguments is String) _tokens.add(call.arguments as String);
        case 'onNotificationTap':
          _opened.add(_stringMap(call.arguments));
      }
      return null;
    });
  }

  static const _channel = MethodChannel('ai.dhanz/push');

  @override
  final String platform;
  final _tokens = StreamController<String>.broadcast();
  final _opened = StreamController<Map<String, String>>.broadcast();

  @override
  Future<bool> requestPermission() async => await _channel.invokeMethod<bool>('requestPermission') ?? false;

  @override
  Future<String?> getToken() async {
    try {
      return await _channel.invokeMethod<String>('getToken');
    } on PlatformException catch (e) {
      debugPrint('Push token unavailable: ${e.message}');
      return null;
    }
  }

  @override
  Stream<String> get tokenRefreshes => _tokens.stream;

  @override
  Stream<Map<String, String>> get notificationTaps => _opened.stream;

  @override
  Future<Map<String, String>?> initialNotification() async {
    final data = _stringMap(await _channel.invokeMethod<Object?>('initialNotification'));
    return data.isEmpty ? null : data;
  }
}

/// Null on platforms without push (desktop, tests). `main()` provides the real bridge on phones.
final pushBridgeProvider = Provider<PushBridge?>((ref) => null);

class PushState {
  const PushState({this.supported = false, this.enabled = true, this.registered = false, this.error});

  /// This device and the server can do push notifications.
  final bool supported;

  /// The user's choice (on by default; the OS still asks for permission).
  final bool enabled;
  final bool registered;
  final String? error;
}

/// Registers this phone with the server so it gets "your answer is ready" notifications.
class PushController extends Notifier<PushState> {
  StreamSubscription<String>? _refreshSub;

  PushBridge? get _bridge => ref.read(pushBridgeProvider);

  @override
  PushState build() {
    final userId = ref.watch(authControllerProvider.select((s) => s.value?.id));
    final serverSupports = ref.watch(serverInfoProvider.select((s) => s.value?.features.pushNotifications ?? false));
    ref.onDispose(() => _refreshSub?.cancel());
    final supported = _bridge != null && serverSupports;
    if (supported && userId != null) unawaited(_start());
    return PushState(supported: supported);
  }

  Future<void> _start() async {
    final store = ref.read(secureStoreProvider);
    final enabled = await store.read(StoreKeys.pushEnabled) != 'false';
    if (!ref.mounted) return;
    state = PushState(supported: true, enabled: enabled);
    if (enabled) await _register();
  }

  Future<void> _register() async {
    final bridge = _bridge;
    if (bridge == null) return;
    try {
      if (!await bridge.requestPermission()) {
        if (ref.mounted) {
          state = PushState(
            supported: true,
            enabled: state.enabled,
            error: 'Notifications are blocked in system settings.',
          );
        }
        return;
      }
      final token = await bridge.getToken();
      if (token == null) return;
      await _send(token);
      await _refreshSub?.cancel();
      _refreshSub = bridge.tokenRefreshes.listen((t) => unawaited(_send(t)));
    } on ApiException catch (e) {
      if (ref.mounted) state = PushState(supported: true, enabled: state.enabled, error: e.message);
    }
  }

  Future<void> _send(String token) async {
    final store = ref.read(secureStoreProvider);
    final old = await store.read(StoreKeys.pushToken);
    final api = ref.read(apiClientProvider);
    await api.registerDevice(_bridge!.platform, token, appVersion: await ref.read(appVersionProvider.future));
    if (old != null && old != token) {
      try {
        await api.unregisterDevice(old);
      } on ApiException {
        // the server forgets dead tokens by itself
      }
    }
    await store.write(StoreKeys.pushToken, token);
    if (ref.mounted) state = PushState(supported: true, enabled: true, registered: true);
  }

  Future<void> setEnabled(bool enabled) async {
    final store = ref.read(secureStoreProvider);
    await store.write(StoreKeys.pushEnabled, '$enabled');
    state = PushState(supported: state.supported, enabled: enabled);
    if (enabled) {
      await _register();
      return;
    }
    await _refreshSub?.cancel();
    final token = await store.read(StoreKeys.pushToken);
    if (token == null) return;
    try {
      await ref.read(apiClientProvider).unregisterDevice(token);
      await store.write(StoreKeys.pushToken, null);
    } on ApiException catch (e) {
      state = PushState(supported: state.supported, enabled: false, error: e.message);
    }
  }
}

final pushControllerProvider = NotifierProvider<PushController, PushState>(PushController.new);
