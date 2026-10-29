import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:dhanz_ai/core/api/api_client.dart';
import 'package:dhanz_ai/core/platform/app_version.dart';
import 'package:dhanz_ai/core/platform/desktop.dart';
import 'package:dhanz_ai/core/platform/installer_io.dart';
import 'package:dhanz_ai/core/platform/push.dart';
import 'package:dhanz_ai/core/platform/updates.dart';
import 'package:dhanz_ai/core/providers.dart';
import 'package:dhanz_ai/core/storage/secure_store.dart';
import 'package:dhanz_ai/features/auth/auth_controller.dart';
import 'package:dhanz_ai/features/chat/chat_controller.dart';
import 'package:dhanz_ai/features/conversations/conversations_controller.dart';
import 'package:dhanz_ai/main.dart';
import 'package:dhanz_ai/models/models.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fake_backend.dart';

class FakePushBridge implements PushBridge {
  String? token = 'fcm-token-0001';
  bool allow = true;
  final refreshes = StreamController<String>.broadcast();
  final taps = StreamController<Map<String, String>>.broadcast();

  @override
  String get platform => 'android';

  @override
  Future<bool> requestPermission() async => allow;

  @override
  Future<String?> getToken() async => token;

  @override
  Stream<String> get tokenRefreshes => refreshes.stream;

  @override
  Stream<Map<String, String>> get notificationTaps => taps.stream;

  @override
  Future<Map<String, String>?> initialNotification() async => null;
}

class FakeDesktop extends NoDesktopShell {
  final notified = <String>[];

  @override
  Future<void> notifyReplyReady({required String conversationId, required String title}) async =>
      notified.add(conversationId);
}

void main() {
  late FakeBackend backend;
  late MemorySecureStore store;
  late FakePushBridge push;
  late FakeDesktop desktop;

  List<Override> overrides({String? updatePlatform}) => [
    secureStoreProvider.overrideWithValue(store),
    apiClientProvider.overrideWith(
      (ref) => ApiClient(store: store, baseUrl: 'http://test', clientFactory: backend.client),
    ),
    pushBridgeProvider.overrideWithValue(push),
    desktopShellProvider.overrideWithValue(desktop),
    appVersionProvider.overrideWith((ref) async => '0.3.0'),
    updatePlatformProvider.overrideWithValue(updatePlatform),
  ];

  setUp(() async {
    backend = FakeBackend();
    store = MemorySecureStore();
    push = FakePushBridge();
    desktop = FakeDesktop();
    ChatController.pollInterval = const Duration(milliseconds: 20);
    await ApiClient(
      store: store,
      baseUrl: 'http://test',
      clientFactory: backend.client,
    ).register('ada@example.com', 'correct-horse-9', 'Ada');
  });

  Future<ProviderContainer> container() async {
    final c = ProviderContainer(overrides: overrides());
    addTearDown(c.dispose);
    await c.read(authControllerProvider.future);
    return c;
  }

  Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 100));

  group('background replies', () {
    test('a dropped connection is followed until the server finishes the reply', () async {
      final c = await container();
      final chat = c.read(chatControllerProvider.notifier);
      backend.dropAfterMeta = true;
      await chat.send('Write a long essay');
      var state = c.read(chatControllerProvider);
      expect(state.streaming, isTrue, reason: 'still generating on the server');
      expect(state.notice, contains('still writing'));
      expect(state.error, isNull);

      backend.finishRunningReplies();
      await settle();
      state = c.read(chatControllerProvider);
      expect(state.streaming, isFalse);
      expect(state.messages.last.content, backend.reply);
      expect(state.messages.last.status, MessageStatus.complete);
    });

    test('stop asks the server to stop the reply', () async {
      final c = await container();
      final chat = c.read(chatControllerProvider.notifier);
      backend.dropAfterMeta = true;
      final id = await chat.send('Write a long essay');
      await chat.stop();
      expect(backend.requests, contains('POST /conversations/$id/stop'));
      final state = c.read(chatControllerProvider);
      expect(state.streaming, isFalse);
      expect(state.messages.last.status, MessageStatus.stopped);
      expect(backend.conversations[id]!['messages'].last['status'], 'stopped');
    });

    test('opening a conversation whose reply is still generating resumes it', () async {
      final c = await container();
      backend.dropAfterMeta = true;
      final id = await c.read(chatControllerProvider.notifier).send('Long one');
      await c.read(chatControllerProvider.notifier).open(null);
      expect(c.read(chatControllerProvider).streaming, isFalse);

      await c.read(chatControllerProvider.notifier).open(id);
      expect(c.read(chatControllerProvider).streaming, isTrue);
      backend.finishRunningReplies();
      await settle();
      expect(c.read(chatControllerProvider).messages.last.content, backend.reply);
      expect(c.read(chatControllerProvider).streaming, isFalse);
    });

    test('a finished reply asks the desktop shell to notify', () async {
      final c = await container();
      final id = await c.read(chatControllerProvider.notifier).send('Hi');
      expect(desktop.notified, [id]);
    });
  });

  group('push notifications', () {
    Future<ProviderContainer> signedIn() async {
      backend.pushNotifications = true;
      final c = await container();
      await c.read(serverInfoProvider.future);
      c.listen(pushControllerProvider, (_, _) {});
      await settle();
      return c;
    }

    test('registers the device token, follows token refreshes and can be turned off', () async {
      final c = await signedIn();
      expect(c.read(pushControllerProvider).registered, isTrue);
      expect(backend.devices['fcm-token-0001'], {
        'platform': 'android',
        'token': 'fcm-token-0001',
        'app_version': '0.3.0',
      });

      push
        ..token = 'fcm-token-0002'
        ..refreshes.add('fcm-token-0002');
      await settle();
      expect(backend.devices.keys, ['fcm-token-0002']);

      await c.read(pushControllerProvider.notifier).setEnabled(false);
      expect(backend.devices, isEmpty);
      expect(await store.read(StoreKeys.pushEnabled), 'false');
      await c.read(pushControllerProvider.notifier).setEnabled(true);
      expect(backend.devices.keys, ['fcm-token-0002']);
    });

    test('signing out unregisters the device', () async {
      final c = await signedIn();
      expect(backend.devices, isNotEmpty);
      await c.read(authControllerProvider.notifier).logout();
      expect(backend.devices, isEmpty);
      expect(await store.read(StoreKeys.pushToken), isNull);
    });

    test('denied permission is explained and nothing is registered', () async {
      push.allow = false;
      final c = await signedIn();
      expect(c.read(pushControllerProvider).error, contains('blocked'));
      expect(backend.devices, isEmpty);
    });

    test('servers without push support register nothing', () async {
      final c = await container();
      await c.read(serverInfoProvider.future);
      c.listen(pushControllerProvider, (_, _) {});
      await settle();
      expect(c.read(pushControllerProvider).supported, isFalse);
      expect(backend.devices, isEmpty);
    });
  });

  group('updates', () {
    Future<void> pumpApp(WidgetTester tester) async {
      tester.view.physicalSize = const Size(1280, 900);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(
        ProviderScope(
          overrides: overrides(updatePlatform: 'android'),
          child: const DhanzApp(),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('an available update shows a banner that can be postponed', (tester) async {
      backend.updateInfo = {
        'platform': 'android',
        'latest_version': '0.4.0',
        'update_available': true,
        'mandatory': false,
        'url': 'https://example.com/dhanz.apk',
        'notes': 'Push notifications',
      };
      await pumpApp(tester);
      expect(backend.requests, contains('GET /app/updates'));
      expect(find.text('DHANZ AI 0.4.0 is available.'), findsOneWidget);
      expect(find.text('Push notifications'), findsOneWidget);
      await tester.tap(find.text('Later'));
      await tester.pumpAndSettle();
      expect(find.text('DHANZ AI 0.4.0 is available.'), findsNothing);
    });

    testWidgets('a mandatory update cannot be postponed', (tester) async {
      backend.updateInfo = {
        'platform': 'android',
        'latest_version': '0.4.0',
        'update_available': true,
        'mandatory': true,
        'url': 'https://example.com/dhanz.apk',
      };
      await pumpApp(tester);
      expect(find.textContaining('is required'), findsOneWidget);
      expect(find.text('Later'), findsNothing);
    });

    testWidgets('no banner when up to date', (tester) async {
      await pumpApp(tester);
      expect(find.text('Update'), findsNothing);
    });

    test('installer downloads are verified against the manifest checksum', () async {
      final bytes = utf8.encode('MZ fake installer');
      final good = sha256.convert(bytes).toString();
      final client = MockClient((r) async => http.Response.bytes(bytes, 200));
      final dir = await Directory.systemTemp.createTemp('dhanz_update');
      addTearDown(() => dir.delete(recursive: true));
      final progress = <double>[];

      final file = await downloadVerified(
        Uri.parse('https://example.com/setup.exe'),
        good.toUpperCase(),
        client: client,
        directory: dir,
        onProgress: progress.add,
      );
      expect(await file.readAsBytes(), bytes);
      expect(progress.last, 1.0);

      await expectLater(
        downloadVerified(Uri.parse('https://example.com/setup.exe'), 'ab' * 32, client: client, directory: dir),
        throwsA(isA<FileSystemException>()),
      );
      expect(dir.listSync(), isEmpty, reason: 'a tampered download is deleted');
      await expectLater(
        downloadVerified(Uri.parse('http://example.com/setup.exe'), good, client: client, directory: dir),
        throwsA(isA<HttpException>()),
      );
    });
  });
}
